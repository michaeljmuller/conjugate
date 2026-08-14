"""Background jobs for adding a verb, with progress the UI can watch.

Looking a verb up and writing ~60 example sentences takes long enough (tens of
seconds to a couple of minutes) that the request can't wait on it. ``POST /api/verbs`` starts a job and returns its id; the browser follows
the job's steps over SSE.

The registry is a plain in-process dict, which is enough because the app runs as
a single uvicorn process — the same assumption the rest of the app already makes.
Finished jobs are kept briefly so a reconnecting page can still read the outcome,
and evicted oldest-first so the dict can't grow without bound.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from sqlalchemy import select

from . import llm
from .db import SessionLocal
from .languages import NotAVerb, Paradigm, SourceUnavailable, UnknownWord, get_adapter
from .models import Verb
from .seed import apply_examples, upsert_verb

log = logging.getLogger(__name__)

# How many finished jobs to keep addressable for a reconnecting client.
MAX_RETAINED = 32

PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"
# Terminal, like done/failed: the job stops after the lookup and the client
# decides whether to start another with the check waived.
NEEDS_CONFIRMATION = "needs_confirmation"

STEP_LOOKUP = "look_up"
STEP_DRAFT = "draft"
STEP_REFINE = "refine"
STEP_SAVE = "save"

_STEP_LABELS: list[tuple[str, str]] = [
    (STEP_LOOKUP, "Look up the conjugation"),
    (STEP_DRAFT, "Write example sentences"),
    (STEP_REFINE, "Review and revise the examples"),
    (STEP_SAVE, "Save the verb"),
]


@dataclass
class Step:
    key: str
    label: str
    status: str = PENDING
    detail: str = ""
    done: int | None = None
    total: int | None = None

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "done": self.done,
            "total": self.total,
        }


@dataclass
class Job:
    id: str
    infinitive: str
    status: str = RUNNING  # running | done | failed | needs_confirmation
    error: str = ""
    # Set with NEEDS_CONFIRMATION: what the user is being asked to approve.
    question: str = ""
    verb_id: int | None = None
    # Things worth telling the user afterwards but not worth blocking on —
    # example sentences that stayed weak after the revision rounds.
    notes: list[str] = field(default_factory=list)
    steps: list[Step] = field(
        default_factory=lambda: [Step(key=k, label=l) for k, l in _STEP_LABELS]
    )
    version: int = 0
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    # -- mutation ---------------------------------------------------------

    def step(self, key: str) -> Step:
        return next(s for s in self.steps if s.key == key)

    def update(self, key: str, **changes) -> None:
        step = self.step(key)
        for name, value in changes.items():
            setattr(step, name, value)
        self._touch()

    def note(self, text: str) -> None:
        self.notes.append(text)
        self._touch()

    def finish(self, verb_id: int) -> None:
        self.status, self.verb_id = DONE, verb_id
        self._touch()

    def ask(self, message: str) -> None:
        """Stop and put the decision to the user.

        Terminal: nothing is waiting on an answer, so an abandoned question
        costs nothing. Saying yes starts a fresh job that skips the question.
        """
        self.status, self.question = NEEDS_CONFIRMATION, message
        self._touch()

    def fail(self, key: str, message: str) -> None:
        self.update(key, status=FAILED, detail=message)
        self.status, self.error = FAILED, message
        self._touch()

    def _touch(self) -> None:
        """Bump the version and wake anyone streaming this job."""
        self.version += 1
        previous, self._event = self._event, asyncio.Event()
        previous.set()

    async def wait_for_change(self, seen: int) -> None:
        """Block until ``version`` moves past ``seen``."""
        while self.version <= seen:
            await self._event.wait()

    # -- projection -------------------------------------------------------

    def as_dict(self) -> dict:
        return {
            "job_id": self.id,
            "infinitive": self.infinitive,
            "status": self.status,
            "error": self.error,
            "question": self.question,
            "verb_id": self.verb_id,
            "notes": list(self.notes),
            "steps": [s.as_dict() for s in self.steps],
            "version": self.version,
        }


# --- registry -------------------------------------------------------------

_jobs: "OrderedDict[str, Job]" = OrderedDict()


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def create(infinitive: str) -> Job:
    job = Job(id=uuid.uuid4().hex, infinitive=infinitive)
    _jobs[job.id] = job
    _evict()
    return job


def _evict() -> None:
    """Drop the oldest finished jobs once the registry is over its cap.
    Running jobs are never evicted."""
    while len(_jobs) > MAX_RETAINED:
        for job_id, job in _jobs.items():
            if job.status != RUNNING:
                del _jobs[job_id]
                break
        else:
            return  # everything is still running; leave it alone


# --- the work ------------------------------------------------------------


def start(
    infinitive: str, user_id: int | None, language: str, force: bool = False
) -> Job:
    """Register a job and kick it off in the background.

    Every add stops after the lookup to confirm; ``force`` skips that, and is
    how the client answers yes.
    """
    job = create(normalize_infinitive(infinitive))
    task = asyncio.create_task(_run(job, user_id, language, force))
    # Hold a reference so the task isn't garbage-collected mid-flight.
    job._task = task  # type: ignore[attr-defined]
    return job


async def _run(job: Job, user_id: int | None, language: str, force: bool) -> None:
    adapter = get_adapter(language)
    try:
        paradigm = await _look_up(job, adapter)
        # Confirm before the expensive half. What the lookup found is worth
        # seeing either way — a fully regular verb teaches nothing the model
        # verb hasn't — and writing ~60 example sentences is the wasteful part
        # to undo.
        if not force:
            found = adapter.describe(paradigm)
            job.ask(f"{job.infinitive} {found} Add it?" if found else f"Add {job.infinitive}?")
            return
        slots = await _write_examples(job, paradigm, adapter)
        job.finish(_save(job, paradigm, slots, user_id, adapter))
    except _StepFailed:
        pass  # already recorded on the job
    except Exception as exc:  # noqa: BLE001 - last resort, must not kill the task
        log.exception("add-verb job failed", extra={"infinitive": job.infinitive})
        running = next((s for s in job.steps if s.status == RUNNING), job.steps[-1])
        job.fail(running.key, f"Unexpected error: {exc}")


class _StepFailed(Exception):
    """Raised after a step has recorded its own failure on the job."""


async def _look_up(job: Job, adapter) -> Paradigm:
    job.update(STEP_LOOKUP, status=RUNNING, detail=f"cplp.org · {job.infinitive}")
    try:
        paradigm = await adapter.paradigm(job.infinitive)
    except NotAVerb:
        job.fail(STEP_LOOKUP, f'"{job.infinitive}" is not a verb.')
        raise _StepFailed from None
    except UnknownWord:
        job.fail(
            STEP_LOOKUP,
            f'No European-Portuguese verb "{job.infinitive}" found. '
            "Check the spelling — a Brazilian form will not be listed.",
        )
        raise _StepFailed from None
    except SourceUnavailable as exc:
        job.fail(STEP_LOOKUP, f"Could not reach cplp.org: {exc}")
        raise _StepFailed from None

    alternatives = sum(1 for c in paradigm.cells.values() if c.alternatives)
    detail = f"{len(paradigm.tenses_present)} tenses · {paradigm.form_count} forms"
    if alternatives:
        detail += f" · {alternatives} with alternatives"
    job.update(STEP_LOOKUP, status=DONE, detail=detail)
    return paradigm


async def _write_examples(job: Job, paradigm: Paradigm, adapter) -> list[dict]:
    def progress(event: str, **kw) -> None:
        if event == "drafting":
            job.update(
                STEP_DRAFT,
                status=RUNNING,
                detail=f"{llm.MODEL} · {kw.get('total', 0)} sentences",
                done=0,
                total=kw.get("total"),
            )
        elif event == "checked":
            job.update(STEP_DRAFT, status=DONE, done=kw.get("total"), total=kw.get("total"))
            flagged, ok, total = kw.get("flagged", 0), kw.get("ok", 0), kw.get("total", 0)
            detail = f"{ok} of {total} good" + (f" · {flagged} to redo" if flagged else "")
            job.update(
                STEP_REFINE,
                status=RUNNING if flagged else DONE,
                detail=detail,
                done=ok,
                total=total,
            )
        elif event == "revising":
            job.update(STEP_REFINE, status=RUNNING, detail=f"rewriting {kw.get('total', 0)}")

    try:
        result = await llm.generate_examples(paradigm, adapter, progress=progress)
    except llm.ExamplesUnavailable as exc:
        # Fatal by design: a verb whose rows have no prompt is worse than no
        # verb, and nothing has been written yet, so failing here leaves the
        # catalogue untouched.
        failed = next((s for s in job.steps if s.status == RUNNING), job.step(STEP_DRAFT))
        job.fail(failed.key, f"Could not write the example sentences. {exc}")
        raise _StepFailed from None

    if result.translation:
        paradigm.translation = result.translation
    if result.unresolved:
        job.update(
            STEP_REFINE,
            status=DONE,
            detail=f"{len(result.unresolved)} left imperfect after {result.rounds} rounds",
        )
        job.note(
            f"{len(result.unresolved)} example sentence(s) still flagged and saved as-is: "
            + ", ".join(f"{p.tense}/{p.person}" for p in result.unresolved[:8])
        )
    else:
        job.update(STEP_REFINE, status=DONE, detail="all sentences check out")
    return llm.example_slots(result)


def _save(
    job: Job, paradigm: Paradigm, slots: list[dict], user_id: int | None, adapter
) -> int:
    """Write the verb — the only step that touches the database, so a failure
    anywhere earlier leaves nothing behind.

    Runs inline on the event loop rather than in a worker thread: it's a single
    verb's worth of inserts, and keeping every ``job.update`` on the loop thread
    means the SSE wakeups stay thread-safe.
    """
    job.update(STEP_SAVE, status=RUNNING, detail="")
    with SessionLocal() as db:
        verb, inserted = upsert_verb(db, paradigm, adapter=adapter, created_by=user_id)
        db.flush()  # assign verb.id and make the new forms visible to apply_examples
        written = apply_examples(verb, slots) // 2  # two columns per sentence pair
        db.commit()
        verb_id = verb.id
    job.update(
        STEP_SAVE,
        status=DONE,
        detail=f"{inserted} forms · {written} example sentence{'' if written == 1 else 's'}",
    )
    return verb_id


def normalize_infinitive(infinitive: str) -> str:
    """Collapse user input to the single lowercase word used as the lookup key."""
    return " ".join(infinitive.split()).strip().lower()


def verb_exists(db, infinitive: str, language: str) -> bool:
    """Is this verb already in the catalogue for that language?

    Scoped by language: the same spelling can be a verb in two of them, and
    having one is no reason to refuse the other.
    """
    return db.scalar(
        select(Verb.id).where(
            Verb.language == language,
            Verb.infinitive == normalize_infinitive(infinitive),
        )
    ) is not None

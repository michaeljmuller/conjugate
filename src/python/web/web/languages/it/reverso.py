"""Read Italian verb paradigms from conjugator.reverso.net.

One request per verb: the whole paradigm is on a single page, no lemma id to
resolve first.

The markup is kind to a parser. Each paradigm sits in a ``blue-box-wrap`` div
carrying ``mobile-title="<Mood> <Tense>"``, so mood and tense are *labels on the
element* rather than something to infer from where the block sits — the failure
mode that makes the cplp.org parser count blocks and columns. Rows are ``<li>``
with the pronoun in ``i.graytxt``, the form in ``i.verbtxt``, the subjunctive's
``che`` in ``i.particletxt``, and, for compound tenses, the auxiliary in
``i.auxgraytxt``.

Three things this layer does *not* do, all of them the adapter's business: it
returns every form a cell lists rather than choosing, it keys blocks by
Reverso's own title, and it says nothing about whether a word is a verb.

**Reverso cannot tell a non-verb from a typo.** ``tavolo`` (a noun) and
``xyzzyq`` (nonsense) both come back 404 on pages identical but for the echoed
word. So there is no ``NotAVerb`` here — only ``WordNotFound``.

**Reverso is not normative**, unlike the vocabulary cplp.org publishes for
Portuguese. It is a commercial aggregator with good tables and no standing, so
nothing downstream should treat its output as beyond question the way the pt
path reasonably does.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

BASE = "https://conjugator.reverso.net/conjugation-italian-verb-{verb}.html"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}
_TIMEOUT = httpx.Timeout(20.0)


class WordNotFound(LookupError):
    """No conjugation published — a typo, or simply not a verb. Reverso does
    not distinguish the two."""


class SourceUnavailable(RuntimeError):
    """Reverso could not be reached, or answered with an unexpected status."""


@dataclass
class RawParadigm:
    """Cells exactly as published, before the adapter selects anything.

    Keyed by ``(reverso_block_title, person)`` — the caller maps the title to a
    tense key, which is also how it drops the blocks it does not drill.
    """

    infinitive: str
    cells: dict[tuple[str, str], list[str]] = field(default_factory=dict)


# The imperative prints no pronouns at all, so its rows are positional. Italian
# has no 1st-person-singular imperative, so the five rows are these:
IMPERATIVE_PERSONS = ["tu", "lui", "noi", "voi", "loro"]

# Personless blocks: one row, no pronoun.
_PERSONLESS = ("Gerundio", "Participio", "Infinito")

_LI_RE = re.compile(r"<li\b[^>]*>(.*?)</li>", re.S)
_BLOCK_RE = re.compile(r'<div[^>]*\bblue-box-wrap\b[^>]*mobile-title="([^"]*)"', re.S)


def _tag_text(fragment: str, cls: str) -> str:
    """Text of the first ``<i class="… cls …">`` in ``fragment``, tags stripped."""
    m = re.search(
        rf'<i[^>]*class="[^"]*\b{cls}\b[^"]*"[^>]*>(.*?)</i>', fragment, re.S
    )
    if not m:
        return ""
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()


def split_forms(text: str) -> list[str]:
    """Split a cell's ``A/B`` notation into its forms.

    ``andare``'s imperative gives ``va'/vai`` — two genuine alternatives, both
    current. Written without surrounding spaces here, unlike cplp.org's
    ``A  /  B``, so the separator is matched loosely.
    """
    return [f for f in (p.strip() for p in re.split(r"\s*/\s*", text)) if f]


def parse_paradigm(page: str, infinitive: str, person_key) -> RawParadigm:
    """Parse every paradigm block on a conjugation page.

    ``person_key`` maps a printed pronoun to an ascii key, returning ``None``
    for anything that isn't one — which is how the imperative's blank pronouns
    are recognised and filled in positionally.

    Raises ``WordNotFound`` when the page carries no paradigm at all, which is
    what a 404 looks like once the chrome is ignored.
    """
    out = RawParadigm(infinitive=infinitive)

    starts = [(m.start(), m.group(1).strip()) for m in _BLOCK_RE.finditer(page)]
    for index, (start, title) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(page)
        rows = _LI_RE.findall(page[start:end])

        positional = 0
        for row in rows:
            forms = split_forms(_tag_text(row, "verbtxt"))
            if not forms:
                continue
            # A compound tense's answer is auxiliary + participle. The drill has
            # no compound tenses — the caller drops those blocks by title — but
            # carrying the auxiliary anyway means that if the title map ever
            # grows, it grows onto "ho parlato" rather than a bare "parlato".
            auxiliary = _tag_text(row, "auxgraytxt")
            if auxiliary:
                forms = [f"{auxiliary} {f}" for f in forms]

            pronoun = _tag_text(row, "graytxt")
            person = person_key(pronoun) if pronoun else None
            if person is None:
                if title.startswith(_PERSONLESS):
                    person = ""  # the caller supplies its own personless key
                elif positional < len(IMPERATIVE_PERSONS):
                    person = IMPERATIVE_PERSONS[positional]
                    positional += 1
                else:
                    continue
            out.cells[(title, person)] = forms

    if not out.cells:
        raise WordNotFound(infinitive)
    return out


class ReversoClient:
    """Fetches from Reverso. One page per verb; no session state to establish."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self._owned = client is None

    async def __aenter__(self) -> "ReversoClient":
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True
            )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owned and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def paradigm(self, word: str, person_key) -> RawParadigm:
        url = BASE.format(verb=quote(word))
        try:
            response = await self._client.get(url)
        except httpx.HTTPError as exc:
            raise SourceUnavailable(str(exc)) from exc
        # An unknown word is a 404 whose body still parses — as nothing. Let it
        # through to the parser so both routes raise the same WordNotFound.
        if response.status_code >= 400 and response.status_code != 404:
            raise SourceUnavailable(f"{url} -> {response.status_code}")
        return parse_paradigm(response.text, word, person_key)

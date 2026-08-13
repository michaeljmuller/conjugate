"""Read verb paradigms from cplp.org, Portugal edition.

The site publishes the orthographic vocabulary that Article 2 of the Acordo
Ortográfico obliges the signatory states to produce. That makes it a normative
reference rather than one more conjugation site with an opinion: measured
against this project's hand-curated seed it matched 700 cells out of 700, where
the conjugation site it replaces got 6 wrong.

Three requests per verb: pin the Portugal edition (a cookie), resolve the word
to a lemma id, then fetch the lemma page. The paradigm sits in a table that is
``display: none`` until the reader clicks "ver flexão", so it is in the HTML on
first load and needs no second fetch.

A cell may legitimately hold several forms, written ``A  /  B`` — ``oiço / ouço``,
``falámos / falamos``, ``aceitado / aceite / aceito``. Everything here returns
lists and leaves the choosing to the language adapter; the notation covers three
unrelated phenomena (a variety split, free variation, and forms governed by
grammar) and this layer cannot tell them apart.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

BASE = "https://voc.cplp.org/index.php"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}
_TIMEOUT = httpx.Timeout(20.0)

# Row labels in the paradigm tables -> this project's ascii person keys.
_PERSONS = {
    "eu": "eu",
    "tu": "tu",
    "ele/ela": "ele",
    "nós": "nos",
    "vós": "vos",
    "eles/elas": "eles",
}

# The page lays the paradigm out as four blocks of columns, each restarting at
# "eu". The first three are three-column grids; the fourth is irregular and is
# handled separately.
_BLOCKS = [
    ["present_indicative", "past_imperfect_indicative", "preterite"],
    ["past_pluperfect", "future_indicative", "conditional"],
    ["present_subjunctive", "past_imperfect_subjunctive", "future_subjunctive"],
]

# Headings inside the fourth block, which interrupt the person rows.
_NOMINAL_HEADINGS = ("Infinitivo", "Gerúndio", "Particípio passado")


class LookupError_(LookupError):
    """Base for the two ways a lookup can come back empty."""


class WordNotFound(LookupError_):
    """No entry at all — a typo, or a form used somewhere other than Portugal."""


class NotAVerb(LookupError_):
    """The word exists but has no verb sense (``mesa`` is a noun)."""


class SourceUnavailable(RuntimeError):
    """cplp.org could not be reached, or answered with an error status."""


@dataclass(frozen=True)
class Lemma:
    id: str
    word: str
    senses: tuple[str, ...]  # parts of speech, e.g. ("verbo", "masculino")

    @property
    def is_verb(self) -> bool:
        return any(s.startswith("verbo") for s in self.senses)


@dataclass
class RawParadigm:
    """Cells exactly as published, before any language-specific selection."""

    infinitive: str
    cells: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    # Personless, and published as a single unsplit set: for `aceitar` the past
    # participle cell holds the regular form and both short ones together.
    past_participle: list[str] = field(default_factory=list)
    present_participle: list[str] = field(default_factory=list)


def _forms(text: str) -> list[str]:
    """Split a cell's ``A  /  B`` notation into its forms."""
    return [f for f in (p.strip() for p in re.split(r"\s*/\s*", text)) if f]


def split_imperative(text: str) -> tuple[list[str], list[str]]:
    """``(affirmative, negative)`` from an imperative cell.

    The negative is parenthesised, and *either* side may carry variants:
    ``vê (vejas)`` but also ``traz  /  traze (tragas)``. Peel the parentheses
    off first, then split each side — doing it the other way round is what the
    earlier ``^(\\S+)\\s*\\((\\S+)\\)$`` attempt got wrong, leaving `trazer`'s
    negative buried inside the affirmative string. A cell with no parentheses
    uses the same form for both.
    """
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", text)
    if not m:
        forms = _forms(text)
        return forms, list(forms)
    return _forms(m.group(1)), _forms(m.group(2))


def _lines(page: str) -> list[str]:
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    return [line.strip() for line in text.split("\n") if line.strip()]


def parse_lemmas(page: str) -> list[Lemma]:
    """Candidate lemmas from a search result.

    A word with one sense redirects straight through (the page carries a
    ``action=lemma&id=N`` javascript redirect); an ambiguous one such as ``ver``
    lists its senses, each linking with ``action=lemma&lemma=N``.
    """
    redirect = re.search(r"action=lemma&id=(\d+)", page)
    if redirect:
        return [Lemma(id=redirect.group(1), word="", senses=())]

    out: list[Lemma] = []
    by_id: dict[str, list[str]] = {}
    order: list[tuple[str, str]] = []
    for lid, word, pos in re.findall(
        r'action=lemma&lemma=(\d+)"[^>]*>\s*<b>[■\s]*([^<]*)</b>\s*</a>\s*-\s*'
        r"<span[^>]*>([^<]+)</span>",
        page,
        re.S,
    ):
        pos = pos.strip()
        if lid not in by_id:
            by_id[lid] = []
            order.append((lid, word.strip()))
        by_id[lid].append(pos)
    for lid, word in order:
        out.append(Lemma(id=lid, word=word, senses=tuple(by_id[lid])))
    return out


def parse_paradigm(page: str, infinitive: str) -> RawParadigm:
    """Parse a lemma page's flexão table."""
    lines = _lines(page)
    start = next((n for n, l in enumerate(lines) if l.endswith("flexão")), None)
    if start is None:
        raise WordNotFound(infinitive)
    lines = lines[start:]

    out = RawParadigm(infinitive=infinitive)
    block = -1
    n = 0
    while n < len(lines):
        label = lines[n]
        if label not in _PERSONS:
            n += 1
            continue

        person = _PERSONS[label]
        if person == "eu":  # every table restarts at eu
            block += 1

        if block < len(_BLOCKS):
            for column, tense in enumerate(_BLOCKS[block]):
                index = n + 1 + column
                if index >= len(lines):
                    break
                value = lines[index]
                if value in _PERSONS or value.startswith("▶"):
                    break
                out.cells[(tense, person)] = _forms(value)
            n += 1 + len(_BLOCKS[block])
            continue

        # Fourth block: imperative (negative in parentheses), inflected
        # infinitive, and — interleaved after the eu row — the nominal forms.
        values: list[str] = []
        end = n + 1
        while end < len(lines) and lines[end] not in _PERSONS and not lines[end].startswith("▶"):
            values.append(lines[end])
            end += 1
        cells = [v for v in values if v not in _NOMINAL_HEADINGS]

        if person == "eu":
            # No imperative for eu; the first value is the inflected infinitive.
            if cells:
                out.cells[("personal_infinitive", "eu")] = _forms(cells[0])
            for heading, key in (
                ("Gerúndio", "present_participle"),
                ("Particípio passado", "past_participle"),
            ):
                if heading in values:
                    at = values.index(heading)
                    if at + 1 < len(values):
                        setattr(out, key, _forms(values[at + 1]))
        else:
            if cells:
                affirmative, negative = split_imperative(cells[0])
                out.cells[("imperative_affirmative", person)] = affirmative
                out.cells[("imperative_negative", person)] = negative
            if len(cells) > 1:
                out.cells[("personal_infinitive", person)] = _forms(cells[1])
        n = end

    if not out.cells:
        raise WordNotFound(infinitive)
    return out


class CplpClient:
    """Fetches from cplp.org. One instance per lookup; the edition is a cookie."""

    def __init__(self, edition: str = "pt", client: httpx.AsyncClient | None = None):
        self.edition = edition
        self._client = client
        self._owned = client is None
        self._pinned = False

    async def __aenter__(self) -> "CplpClient":
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True
            )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owned and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, url: str) -> str:
        try:
            response = await self._client.get(url)
        except httpx.HTTPError as exc:
            raise SourceUnavailable(str(exc)) from exc
        if response.status_code >= 400:
            raise SourceUnavailable(f"{url} -> {response.status_code}")
        return response.text

    async def _pin_edition(self) -> None:
        """Select the national edition. Only affects the lemma inventory — the
        paradigm tables are identical across editions — but it is what makes a
        Brazilian-only word report as absent."""
        if not self._pinned:
            await self._get(f"{BASE}?action=von&csl={self.edition}")
            self._pinned = True

    async def lookup(self, word: str) -> Lemma:
        """Resolve a word to its verb lemma."""
        await self._pin_edition()
        page = await self._get(
            f"{BASE}?action=simplesearch&query={quote(word)}&sel=exact"
        )
        candidates = parse_lemmas(page)
        if not candidates:
            raise WordNotFound(word)
        verbs = [c for c in candidates if c.is_verb]
        if verbs:
            return verbs[0]
        # A single-sense redirect carries no part of speech, so it can only be
        # checked once the lemma page is open; anything else really is not a verb.
        if len(candidates) == 1 and not candidates[0].senses:
            return candidates[0]
        raise NotAVerb(word)

    async def paradigm(self, word: str) -> RawParadigm:
        lemma = await self.lookup(word)
        page = await self._get(f"{BASE}?action=lemma&id={lemma.id}")
        return parse_paradigm(page, word)

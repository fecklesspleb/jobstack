"""Dictionary-based technology tagging for job posts.

Rules, in order:
1. Whole-word matching. A spelling counts only when it is not glued to a letter, digit or '_'
   on either side: 'AWS' does not match 'laws', 'SAP' does not match 'ASAP', but 'Okta' matches
   'Okta-based SSO'.
2. Longest match wins. 'Jira Service Management' is one tag, not 'Jira' plus extra words.
3. Everyday words (Slack, Zoom, Git, Notion...) are listed under caseSensitive and only match with
   their usual capitalization.
4. ignoreIn phrases: a match inside 'Ivanti Endpoint Manager' is not Microsoft Intune.
5. Sentences that list the employer's customers or investors are skipped
   ('trusted by companies like Okta and Notion' says nothing about the employer's own stack).
6. Gated spellings (Slack, Zoom, Microsoft Teams, Webex) only count inside a requirements section
   or next to a phrase such as 'experience with'. 'Chat with us on Slack' does not count.
7. The employer's own name is dropped: a Datadog job that mentions Datadog is not a Datadog signal.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from importlib import resources
from pathlib import Path
from typing import Any, Iterable

_B = r'(?<![A-Za-z0-9_])'
_E = r'(?![A-Za-z0-9_])'

CUSTOMER_LIST_RE = re.compile(
    r"\b(?:customers?|clients?|companies|brands|logos|organi[sz]ations)\s*,?\s*(?:like|such\s+as|including|include)\b"
    r"|\btrusted\s+by\b|\bbacked\s+by\b|\binvestors?\b|\bcustomers?\s+include\b",
    re.I)
SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+|\n+')
REQ_PHRASE_RE = re.compile(
    r"\b(?:experience\s+(?:with|in|using|administering|managing|supporting|deploying|configuring)"
    r"|hands-on\s+(?:experience\s+)?with|proficien(?:t|cy)\s+(?:in|with)|expertise\s+(?:in|with)|knowledge\s+of"
    r"|familiar(?:ity)?\s+with|administ(?:er|ering|ration|rator)|manag(?:e|es|ing)|support(?:s|ing)?"
    r"|configur(?:e|es|ing)|deploy(?:s|ing)?|troubleshoot(?:s|ing)?|maintain(?:s|ing)?)\b", re.I)
REQ_HEADING_RE = re.compile(
    r"requirement|qualification|what\s+you(?:'ll|\s+will)?\s+(?:bring|need)|who\s+you\s+are|about\s+you\b"
    r"|must[\s-]haves?|nice[\s-]to[\s-]haves?|preferred|skills|tech(?:nology|nical)?\s+stack|our\s+stack", re.I)
OTHER_HEADING_RE = re.compile(
    r"^(?:about|benefits|perks|what\s+you(?:'ll|\s+will)\s+do|responsibilities|the\s+role|the\s+team|our\s+team"
    r"|interview|compensation|salary|pay|why|life\s+at|culture|values|how\s+we)", re.I)
REQ_WINDOW = 80


def _norm(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', s.lower())


class _TextParser(HTMLParser):
    BLOCK = {'p', 'div', 'br', 'li', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr', 'section'}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self.BLOCK:
            self.parts.append('\n')

    def handle_endtag(self, tag: str) -> None:
        if tag in self.BLOCK:
            self.parts.append('\n')

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(markup: str | None) -> str:
    """Plain text from job-post HTML. Handles Greenhouse's entity-escaped HTML too."""
    if not markup:
        return ''
    if '&lt;' in markup and '<' not in markup:
        markup = html.unescape(markup)
    p = _TextParser()
    p.feed(markup)
    p.close()
    text = ''.join(p.parts).replace('\xa0', ' ')
    lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in text.split('\n')]
    return '\n'.join(ln for ln in lines if ln)


def load_dictionary(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        raw = resources.files('jobstack').joinpath('data/tech_dictionary.json').read_text(encoding='utf-8')
    else:
        raw = Path(path).read_text(encoding='utf-8')
    data = json.loads(raw)
    seen: set[str] = set()
    for e in data['entries']:
        if e['tag'] in seen:
            raise ValueError(f"duplicate tag in dictionary: {e['tag']}")
        seen.add(e['tag'])
        if not (e.get('aliases') or e.get('caseSensitive')):
            raise ValueError(f"tag has no spellings: {e['tag']}")
    return data


@dataclass
class Tagger:
    entries: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.category: dict[str, str] = {}
        self._ci: dict[str, str] = {}
        self._cs: dict[str, str] = {}
        self._ignore: dict[str, list[re.Pattern[str]]] = {}
        self._gated: set[str] = set()
        self._keys: dict[str, set[str]] = {}
        for e in self.entries:
            self._add(e)
        self._compile()

    @classmethod
    def default(cls) -> 'Tagger':
        return cls(load_dictionary()['entries'])

    @classmethod
    def from_file(cls, path: str | Path) -> 'Tagger':
        return cls(load_dictionary(path)['entries'])

    def _add(self, e: dict[str, Any]) -> None:
        tag = e['tag']
        self.category.setdefault(tag, e.get('category', 'custom'))
        keys = self._keys.setdefault(tag, {_norm(tag)})
        for a in e.get('aliases', []):
            self._ci.setdefault(a.lower(), tag)
            keys.add(_norm(a))
        for a in e.get('caseSensitive', []):
            self._cs.setdefault(a, tag)
            keys.add(_norm(a))
        for a in e.get('gated', []):
            self._gated.add(a.lower())
        if e.get('ignoreIn'):
            self._ignore[tag] = [re.compile(_B + re.escape(p) + _E, re.I) for p in e['ignoreIn']]

    def add_terms(self, terms: Iterable[str]) -> None:
        """Add custom terms. 'Tag=alias1|alias2' gives one tag several spellings."""
        for raw in terms:
            tag, _, rest = str(raw).partition('=')
            tag = tag.strip()
            if not tag:
                continue
            aliases = [a.strip() for a in rest.split('|') if a.strip()] if rest else []
            self._add({'tag': tag, 'category': 'custom', 'aliases': aliases + [tag]})
        self._compile()

    def _compile(self) -> None:
        def rx(terms: Iterable[str], flags: int) -> re.Pattern[str] | None:
            ts = sorted(set(terms), key=lambda t: (-len(t), t))
            return re.compile(_B + '(' + '|'.join(map(re.escape, ts)) + ')' + _E, flags) if ts else None
        self._ci_re = rx(self._ci, re.I)
        self._cs_re = rx(self._cs, 0)

    @property
    def size(self) -> int:
        return len(self.category)

    def spans(self, text: str | None) -> list[tuple[int, int, str]]:
        """Non-overlapping (start, end, tag) matches, longest first at each position."""
        if not text:
            return []
        found: list[tuple[int, int, str]] = []
        if self._ci_re:
            found += [(m.start(), m.end(), self._ci[m.group(1).lower()]) for m in self._ci_re.finditer(text)]
        if self._cs_re:
            found += [(m.start(), m.end(), self._cs[m.group(1)]) for m in self._cs_re.finditer(text)]
        found.sort(key=lambda s: (s[0], -(s[1] - s[0])))
        out: list[tuple[int, int, str]] = []
        end = -1
        for a, b, tag in found:
            if a < end:
                continue
            if any(p.start() <= a and b <= p.end() for rx in self._ignore.get(tag, ()) for p in rx.finditer(text)):
                continue
            end = b
            out.append((a, b, tag))
        return out

    def find(self, text: str | None) -> dict[str, int]:
        """tag -> mention count, with matching rules 1-4 only (no sentence context)."""
        counts: dict[str, int] = {}
        for _, _, tag in self.spans(text):
            counts[tag] = counts.get(tag, 0) + 1
        return counts

    def own_tags(self, *company_names: str | None) -> set[str]:
        """Tags that are the employer's own name."""
        keys = {_norm(n) for n in company_names if n and _norm(n)}
        keys |= {_norm(re.sub(r',?\s+(inc|llc|ltd|corp|corporation)\.?$', '', n, flags=re.I))
                 for n in company_names if n}
        return {t for t, ks in self._keys.items() if ks & keys}

    def _heading(self, line: str) -> bool | None:
        """True for a requirements heading, False for another heading, None for body text."""
        t = line.strip().strip('*#_ ').strip()
        if not t or len(t) > 60 or t.endswith(('.', ',', ';')) or t[0] in '-\u2022*':
            return None
        shaped = t.endswith(':') or (sum(c.isalpha() for c in t) >= 4 and t.upper() == t)
        if not shaped and (len(t.split()) > 6 or self.spans(t)):
            return None
        if REQ_HEADING_RE.search(t):
            return True
        return False if shaped or OTHER_HEADING_RE.search(t) else None

    def tag(self, title: str | None = None, text: str | None = None, company: str | None = None) -> dict[str, Any]:
        """Tag one job post. Returns tags sorted by mentions, their categories and counts."""
        counts: dict[str, int] = {}
        for _, _, t in self.spans(title):
            counts[t] = counts.get(t, 0) + 1
        in_req = False
        for line in (text or '').split('\n'):
            heading = self._heading(line)
            if heading is not None:
                in_req = heading
                continue
            inline = re.match(r'^\W*([^:\n]{1,50}):\s+\S', line)
            if inline and REQ_HEADING_RE.search(inline.group(1)):
                in_req = True   # "Requirements: Okta, Intune" on one line
            for sent in SENTENCE_SPLIT_RE.split(line):
                if not sent.strip() or CUSTOMER_LIST_RE.search(sent):
                    continue
                req = [(m.start(), m.end()) for m in REQ_PHRASE_RE.finditer(sent)]
                for a, b, t in self.spans(sent):
                    if sent[a:b].lower() in self._gated and not in_req and not any(
                            a - REQ_WINDOW <= e <= a or b <= s <= b + REQ_WINDOW // 2 for s, e in req):
                        continue
                    counts[t] = counts.get(t, 0) + 1
        for t in self.own_tags(company):
            counts.pop(t, None)
        tags = sorted(counts, key=lambda t: (-counts[t], t))
        return {'tags': tags, 'categories': sorted({self.category[t] for t in tags}),
                'mentions': {t: counts[t] for t in tags}}

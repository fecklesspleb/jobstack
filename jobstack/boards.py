"""Read public Greenhouse, Lever and Ashby job boards (no keys, no login).

Endpoints:
  Greenhouse  https://boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true
  Lever       https://api.lever.co/v0/postings/<slug>?mode=json&limit=100&skip=<n>
  Ashby       https://api.ashbyhq.com/posting-api/job-board/<slug>

The fetcher reads each host's robots.txt first and skips the host if it disallows the path,
waits at least `min_interval` seconds between requests (1.0 by default) and sends a User-Agent
that names the tool. Parsing is separate from fetching, so it can be tested offline.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from typing import Any, Callable

from .tagger import html_to_text

USER_AGENT = 'jobstack/0.1 (+https://github.com/fecklesspleb/jobstack)'
LEVER_PAGE = 100
ATS = ('greenhouse', 'lever', 'ashby')


@dataclass
class Job:
    ats: str
    company: str
    id: str
    title: str
    url: str
    location: str
    text: str

    def as_dict(self) -> dict[str, str]:
        return dict(self.__dict__)


def parse_board(spec: str) -> tuple[str, str]:
    """'greenhouse:gitlab' -> ('greenhouse', 'gitlab')."""
    ats, sep, slug = spec.partition(':')
    ats, slug = ats.strip().lower(), slug.strip()
    if not sep or ats not in ATS or not slug or '/' in slug:
        raise ValueError(f'expected greenhouse:<slug>, lever:<slug> or ashby:<slug>, got {spec!r}')
    return ats, slug


def board_url(ats: str, slug: str, skip: int = 0) -> str:
    q = urllib.parse.quote(slug)
    if ats == 'greenhouse':
        return f'https://boards-api.greenhouse.io/v1/boards/{q}/jobs?content=true'
    if ats == 'lever':
        return f'https://api.lever.co/v0/postings/{q}?mode=json&limit={LEVER_PAGE}&skip={skip}'
    if ats == 'ashby':
        return f'https://api.ashbyhq.com/posting-api/job-board/{q}'
    raise ValueError(ats)


def parse_greenhouse(data: dict[str, Any], slug: str) -> list[Job]:
    out = []
    for j in data.get('jobs', []):
        out.append(Job('greenhouse', j.get('company_name') or slug, str(j.get('id', '')), j.get('title') or '',
                       j.get('absolute_url') or '', (j.get('location') or {}).get('name') or '',
                       html_to_text(j.get('content'))))
    return out


def parse_lever(data: list[dict[str, Any]], slug: str) -> list[Job]:
    out = []
    for j in data:
        parts = [html_to_text(j.get('description'))]
        for lst in j.get('lists') or []:
            parts.append(f"{lst.get('text', '')}:")
            parts.append(html_to_text(lst.get('content')))
        if j.get('additional'):
            parts.append('Additional information:')    # ends the last list section
            parts.append(html_to_text(j.get('additional')))
        out.append(Job('lever', slug, str(j.get('id', '')), j.get('text') or '', j.get('hostedUrl') or '',
                       (j.get('categories') or {}).get('location') or '', '\n'.join(p for p in parts if p)))
    return out


def parse_ashby(data: dict[str, Any], slug: str) -> list[Job]:
    out = []
    for j in data.get('jobs', []):
        if j.get('isListed') is False:
            continue
        text = html_to_text(j.get('descriptionHtml')) or (j.get('descriptionPlain') or '')
        out.append(Job('ashby', slug, str(j.get('id', '')), j.get('title') or '', j.get('jobUrl') or '',
                       j.get('location') or '', text))
    return out


class Fetcher:
    """Polite JSON GETs: robots.txt per host, a minimum gap between requests, a clear User-Agent."""

    def __init__(self, min_interval: float = 1.0, timeout: float = 30.0,
                 opener: Callable[..., Any] | None = None, log: Callable[[str], None] | None = None) -> None:
        self.min_interval = min_interval
        self.timeout = timeout
        self.opener = opener or urllib.request.urlopen
        self.log = log or (lambda msg: None)
        self.requests = 0
        self._last = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def _wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.monotonic()

    def _get(self, url: str) -> tuple[int, str]:
        self._wait()
        self.requests += 1
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
        try:
            with self.opener(req, timeout=self.timeout) as r:
                status = r.status
                body = r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            status, body = e.code, ''
        self.log(f'GET {url} -> {status}')
        return status, body

    def allowed(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        origin = f'{parts.scheme}://{parts.netloc}'
        if origin not in self._robots:
            status, body = self._get(origin + '/robots.txt')
            if 400 <= status < 500:
                rp = None                       # RFC 9309: no robots.txt, no rules
            elif status == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(body.splitlines())
            else:
                raise RuntimeError(f'robots.txt for {origin} returned {status}; skipping host')
            self._robots[origin] = rp
        rp = self._robots[origin]
        return rp is None or rp.can_fetch(USER_AGENT, url)

    def get_json(self, url: str) -> Any:
        if not self.allowed(url):
            raise PermissionError(f'robots.txt disallows {url}')
        status, body = self._get(url)
        if status != 200:
            raise RuntimeError(f'{url} returned HTTP {status}')
        return json.loads(body)

    def jobs(self, spec: str, max_lever_pages: int = 5) -> list[Job]:
        ats, slug = parse_board(spec)
        if ats == 'greenhouse':
            return parse_greenhouse(self.get_json(board_url(ats, slug)), slug)
        if ats == 'ashby':
            return parse_ashby(self.get_json(board_url(ats, slug)), slug)
        out: list[Job] = []
        for page in range(max_lever_pages):
            batch = self.get_json(board_url(ats, slug, page * LEVER_PAGE))
            out += parse_lever(batch, slug)
            if len(batch) < LEVER_PAGE:
                break
        return out

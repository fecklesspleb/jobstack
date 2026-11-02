"""Per-company tables: how many open jobs mention each tool."""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable

from .boards import Job
from .tagger import Tagger


def tag_jobs(tagger: Tagger, jobs: Iterable[Job]) -> list[dict[str, Any]]:
    rows = []
    for j in jobs:
        r = tagger.tag(j.title, j.text, company=j.company)
        rows.append({**j.as_dict(), 'tags': r['tags'], 'categories': r['categories']})
    return rows


def company_table(rows: list[dict[str, Any]], focus: list[str]) -> list[dict[str, Any]]:
    """One row per company: total jobs and jobs mentioning each focus tag."""
    table: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = f"{r['ats']}:{r['company']}"
        t = table.setdefault(key, {'board': key, 'jobs': 0, **{f: 0 for f in focus}})
        t['jobs'] += 1
        for f in focus:
            if f in r['tags']:
                t[f] += 1
    return sorted(table.values(), key=lambda t: (-sum(t[f] for f in focus), t['board']))


def to_markdown(table: list[dict[str, Any]]) -> str:
    if not table:
        return ''
    cols = list(table[0])
    lines = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    lines += ['| ' + ' | '.join(str(r[c]) for c in cols) + ' |' for r in table]
    return '\n'.join(lines) + '\n'


def to_csv(table: list[dict[str, Any]]) -> str:
    if not table:
        return ''
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(table[0]), lineterminator='\n')
    w.writeheader()
    w.writerows(table)
    return buf.getvalue()

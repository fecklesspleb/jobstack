"""Command line: `jobstack tag` for text, `jobstack boards` for live job boards."""

from __future__ import annotations

import argparse
import json
import sys

from .boards import Fetcher
from .report import company_table, tag_jobs, to_csv, to_markdown
from .tagger import Tagger


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog='jobstack', description='Tag job posts with the tools they name.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('tag', help='tag text from an argument or stdin')
    t.add_argument('text', nargs='?', help='text to tag (default: read stdin)')
    t.add_argument('--title', default=None)
    t.add_argument('--company', default=None, help="employer name; its own product is not tagged")
    b = sub.add_parser('boards', help='fetch public job boards and print a per-company table')
    b.add_argument('board', nargs='+', help='greenhouse:<slug>, lever:<slug> or ashby:<slug>')
    b.add_argument('--focus', default='Okta,Microsoft Intune', help='comma-separated tags to count')
    b.add_argument('--format', choices=['md', 'csv', 'json'], default='md')
    b.add_argument('--jobs-out', default=None, help='also write every tagged job as JSON lines here')
    b.add_argument('--min-interval', type=float, default=1.0, help='seconds between requests (min 1.0)')
    for p in (t, b):
        p.add_argument('--dictionary', default=None, help='path to a custom dictionary JSON')
        p.add_argument('--term', action='append', default=[], help="extra term, e.g. 'Rippling' or 'Kolide=Kolide|1Password XAM'")
    a = ap.parse_args(argv)

    tagger = Tagger.from_file(a.dictionary) if a.dictionary else Tagger.default()
    if a.term:
        tagger.add_terms(a.term)

    if a.cmd == 'tag':
        text = a.text if a.text is not None else sys.stdin.read()
        print(json.dumps(tagger.tag(a.title, text, company=a.company), indent=2))
        return 0

    focus = [f.strip() for f in a.focus.split(',') if f.strip()]
    unknown = [f for f in focus if f not in tagger.category]
    if unknown:
        ap.error(f'unknown tag(s): {", ".join(unknown)}')
    fetcher = Fetcher(min_interval=max(1.0, a.min_interval), log=lambda m: print(m, file=sys.stderr))
    rows = []
    for spec in a.board:
        try:
            rows += tag_jobs(tagger, fetcher.jobs(spec))
        except (RuntimeError, PermissionError, ValueError) as e:
            print(f'{spec}: skipped ({e})', file=sys.stderr)
    if a.jobs_out:
        with open(a.jobs_out, 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    table = company_table(rows, focus)
    out = {'md': to_markdown, 'csv': to_csv, 'json': lambda tb: json.dumps(tb, indent=2) + '\n'}[a.format](table)
    sys.stdout.write(out)
    print(f'{fetcher.requests} requests', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

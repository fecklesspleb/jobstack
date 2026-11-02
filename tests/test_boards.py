import io
import json
import urllib.error

import pytest

from jobstack.boards import Fetcher, board_url, parse_ashby, parse_board, parse_greenhouse, parse_lever
from jobstack.report import company_table, tag_jobs, to_csv, to_markdown


def test_parse_board_spec():
    assert parse_board('greenhouse:gitlab') == ('greenhouse', 'gitlab')
    assert parse_board(' Lever:acme ') == ('lever', 'acme')


@pytest.mark.parametrize('bad', ['gitlab', 'workday:acme', 'ashby:', 'lever:a/b'])
def test_parse_board_rejects_bad_specs(bad):
    with pytest.raises(ValueError):
        parse_board(bad)


def test_board_urls():
    assert board_url('greenhouse', 'acme') == 'https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true'
    assert board_url('lever', 'acme', 100) == 'https://api.lever.co/v0/postings/acme?mode=json&limit=100&skip=100'
    assert board_url('ashby', 'acme') == 'https://api.ashbyhq.com/posting-api/job-board/acme'


def test_parse_greenhouse(fixture_json, tagger):
    jobs = parse_greenhouse(fixture_json('greenhouse_examplerobotics.json'), 'examplerobotics')
    assert [j.title for j in jobs] == ['IT Systems Engineer', 'Account Executive']
    assert jobs[0].company == 'Example Robotics' and jobs[0].location == 'Remote - US'
    r = tagger.tag(jobs[0].title, jobs[0].text, jobs[0].company)
    assert set(r['tags']) == {'Okta', 'Microsoft Intune', 'Jamf', 'CrowdStrike', 'SCIM'}   # Slack is in Benefits
    r2 = tagger.tag(jobs[1].title, jobs[1].text, jobs[1].company)
    assert r2['tags'] == ['Salesforce']                                        # customer list skipped


def test_parse_lever_includes_lists(fixture_json, tagger):
    jobs = parse_lever(fixture_json('lever_examplelever.json'), 'examplelever')
    assert len(jobs) == 1 and jobs[0].title == 'Help Desk Technician'
    r = tagger.tag(jobs[0].title, jobs[0].text, jobs[0].company)
    assert set(r['tags']) == {'Kandji', 'Jamf', 'Google Workspace', 'Zoom', 'macOS'}   # bare 'Windows' is not a tag
    assert r['mentions']['Zoom'] == 1                                          # "over Zoom on Fridays" not counted


def test_parse_ashby_skips_unlisted(fixture_json):
    jobs = parse_ashby(fixture_json('ashby_exampleashby.json'), 'exampleashby')
    assert [j.id for j in jobs] == ['ab-1']


def test_company_table(fixture_json, tagger):
    jobs = (parse_greenhouse(fixture_json('greenhouse_examplerobotics.json'), 'examplerobotics')
            + parse_ashby(fixture_json('ashby_exampleashby.json'), 'exampleashby'))
    table = company_table(tag_jobs(tagger, jobs), ['Okta', 'Microsoft Intune'])
    assert table == [
        {'board': 'greenhouse:Example Robotics', 'jobs': 2, 'Okta': 1, 'Microsoft Intune': 1},
        {'board': 'ashby:exampleashby', 'jobs': 1, 'Okta': 1, 'Microsoft Intune': 0},
    ]
    md = to_markdown(table)
    assert md.splitlines()[0] == '| board | jobs | Okta | Microsoft Intune |'
    assert to_csv(table).splitlines()[1] == 'greenhouse:Example Robotics,2,1,1'


class FakeResponse(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body.encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def make_opener(routes, seen):
    def opener(req, timeout=None):
        seen.append((req.full_url, req.get_header('User-agent')))
        status, body = routes.get(req.full_url, (404, ''))
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, 'x', {}, None)
        return FakeResponse(body, status)
    return opener


def test_fetcher_reads_robots_once_and_sends_user_agent(fixture_json):
    url = board_url('ashby', 'exampleashby')
    routes = {'https://api.ashbyhq.com/robots.txt': (200, 'User-agent: *\nAllow: /\n'),
              url: (200, json.dumps(fixture_json('ashby_exampleashby.json')))}
    seen = []
    f = Fetcher(min_interval=0, opener=make_opener(routes, seen))
    assert len(f.jobs('ashby:exampleashby')) == 1
    assert len(f.jobs('ashby:exampleashby')) == 1
    assert [u for u, _ in seen].count('https://api.ashbyhq.com/robots.txt') == 1
    assert f.requests == 3
    assert all(ua.startswith('jobstack/') for _, ua in seen)


def test_fetcher_obeys_robots_disallow():
    routes = {'https://api.ashbyhq.com/robots.txt': (200, 'User-agent: *\nDisallow: /\n')}
    f = Fetcher(min_interval=0, opener=make_opener(routes, []))
    with pytest.raises(PermissionError):
        f.jobs('ashby:exampleashby')


def test_fetcher_missing_robots_means_allowed(fixture_json):
    url = board_url('greenhouse', 'examplerobotics')
    routes = {url: (200, json.dumps(fixture_json('greenhouse_examplerobotics.json')))}
    f = Fetcher(min_interval=0, opener=make_opener(routes, []))
    assert len(f.jobs('greenhouse:examplerobotics')) == 2


def test_fetcher_http_error_raises():
    routes = {'https://api.lever.co/robots.txt': (404, '')}
    f = Fetcher(min_interval=0, opener=make_opener(routes, []))
    with pytest.raises(RuntimeError):
        f.jobs('lever:nosuchboard')


def test_lever_pagination(fixture_json):
    page = fixture_json('lever_examplelever.json')[0]
    first = [dict(page, id=f'p{i}') for i in range(100)]
    routes = {board_url('lever', 'big', 0): (200, json.dumps(first)),
              board_url('lever', 'big', 100): (200, json.dumps([dict(page, id='last')]))}
    f = Fetcher(min_interval=0, opener=make_opener(routes, []))
    jobs = f.jobs('lever:big')
    assert len(jobs) == 101 and jobs[-1].id == 'last'

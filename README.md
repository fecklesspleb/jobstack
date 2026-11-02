# jobstack

Tag job posts with the tools they ask for (Okta, Intune, Jamf, CrowdStrike and 324 more), then
count which companies are hiring for which tools. It reads the public job-board JSON that
Greenhouse, Lever and Ashby publish for each employer.

- Plain Python 3.9+, no runtime dependencies
- 328-tool dictionary in 20 categories, written by hand ([DICTIONARY.md](DICTIONARY.md))
- Whole-word matching plus rules that drop the common false positives (below)
- MIT license

## Install

```bash
git clone https://github.com/fecklesspleb/jobstack
cd jobstack
pip install -e .
```

## Tag one post

```bash
cat > post.txt <<'TXT'
About us
Trusted by companies like Okta and Notion. Chat with us on Slack any time.

Requirements:
- 3+ years administering Okta and Microsoft Intune (Endpoint Manager)
- Experience with Jamf Pro and CrowdStrike Falcon
- Comfortable in Slack and Zoom
TXT
jobstack tag --title "IT Systems Engineer" --company Acme < post.txt
```

Output:

```json
{
  "tags": ["Microsoft Intune", "CrowdStrike", "Jamf", "Okta", "Slack", "Zoom"],
  "categories": ["collaboration", "endpoint-mgmt", "identity", "security"],
  "mentions": {"Microsoft Intune": 2, "CrowdStrike": 1, "Jamf": 1, "Okta": 1, "Slack": 1, "Zoom": 1}
}
```

Okta is counted once and Notion not at all: the "Trusted by companies like..." sentence is about
customers, so it is skipped. Slack is counted once: the requirements line counts, the "Chat with
us on Slack" line does not. "Intune" and "Endpoint Manager" are two spellings of one tag.

## Count a few companies

A board is `ats:slug`, where the slug is the one in the employer's careers URL
(`boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>`, `jobs.ashbyhq.com/<slug>`).

```bash
jobstack boards greenhouse:discord ashby:ramp --focus "Okta,Microsoft Intune,Jamf"
```

Output from a run on 2026-11-02 (the numbers change as jobs open and close):

```
| board | jobs | Okta | Microsoft Intune | Jamf |
|---|---|---|---|---|
| greenhouse:Discord | 41 | 2 | 2 | 2 |
| ashby:ramp | 173 | 2 | 0 | 2 |
```

Each cell is the number of open postings that mention the tool. `--format csv` or `--format json`
change the output, and `--jobs-out jobs.jsonl` saves every tagged posting.

The fetcher is deliberately slow and polite: it reads each host's robots.txt first, waits at least
1 second between requests (`--min-interval` cannot go lower), sends a `User-Agent` that names this
project, and prints the request count to stderr. Lever boards are read 100 postings per request, up
to 5 pages.

## Python

```python
from jobstack import Tagger

t = Tagger.default()
t.tag("Support Engineer", "Ivanti Endpoint Manager experience required.")
# {'tags': ['Ivanti'], 'categories': ['endpoint-mgmt'], 'mentions': {'Ivanti': 1}}

t.find("Must comply with state laws. Reply ASAP. Trust and safety. Go-to-market.")
# {}

t.add_terms(["Kolide=Kolide|1Password XAM"])
t.tag("", "Experience with 1Password XAM")["tags"]
# ['Kolide']
```

`jobstack.boards.Fetcher` and `jobstack.report.company_table` do what the `boards` command does,
if you want the rows in your own code.

## Matching rules

1. **Whole words.** A spelling only counts when no letter, digit or `_` touches it: `AWS` does not
   match "laws", `SAP` does not match "ASAP", `Rust` does not match "trust".
2. **Longest match wins.** "Jira Service Management" is one tag, not Jira plus leftovers.
3. **Case-sensitive everyday words.** `Slack`, `Zoom`, `Git`, `Rust`, `Notion` and similar only
   match with their usual capitals.
4. **ignoreIn phrases.** "Ivanti Endpoint Manager" is Ivanti, not Microsoft Intune.
5. **Customer and investor sentences are skipped.** "Trusted by companies like Okta" says nothing
   about the employer's own tools.
6. **Gated tools.** Slack, Zoom, Microsoft Teams and Webex only count inside a requirements
   section or near a phrase such as "experience with".
7. **The employer's own name is dropped.** A Datadog posting that mentions Datadog is not a
   Datadog signal.

Rules 5 and 6 rely on headings and phrases, so they are heuristics: a post with no headings, or
with an unusual heading, can still let a culture line through. `Tagger.find()` applies rules 1 to 4
only, if you want raw mentions.

## Tests

```bash
pip install -e ".[test]"
pytest -q
```

The tests run offline against small hand-made board files in `tests/fixtures/`. CI runs them on
Python 3.9, 3.11 and 3.13.

## Contributing

Missing a tool, or found a false positive? Open an issue with the posting text (or a link to it)
and what you expected. For dictionary changes see [DICTIONARY.md](DICTIONARY.md).

## License

MIT. See [LICENSE](LICENSE). This code and README were written with AI assistance.

My IT Hiring Signals Actor on Apify runs this kind of tagging across public ATS job boards at $0.0015 per tagged job ($1.50 per 1,000). I built both.

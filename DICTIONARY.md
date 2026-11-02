# The jobstack dictionary

`jobstack/data/tech_dictionary.json` lists 328 tools in 20 categories. It is released under the
MIT license, like the rest of this repo.

## Where it comes from

The list was written by hand by the jobstack maintainer (fecklesspleb). It started as the
dictionary in the maintainer's own job-tagging tool and was copied over from that code. No
third-party lists, datasets or scraped vendor directories were copied into it. Tool names are
product names; the trademarks belong to their owners.

## Format

```json
{
  "tag": "Microsoft Intune",
  "category": "endpoint-mgmt",
  "aliases": ["Intune", "Microsoft Intune", "Microsoft Endpoint Manager", "Endpoint Manager"],
  "caseSensitive": ["MEM"],
  "ignoreIn": ["Ivanti Endpoint Manager", "Symantec Endpoint Manager", "Endpoint Manager Plus"]
}
```

| field | meaning |
|---|---|
| `tag` | the name that shows up in results |
| `category` | one of the 20 categories below |
| `aliases` | other spellings, matched without regard to case, as whole words |
| `caseSensitive` | spellings that only match with this exact capitalization; used for everyday words such as `Slack`, `Zoom`, `Git`, `Rust`, `Notion` |
| `gated` | spellings that only count inside a requirements section or next to a phrase such as "experience with" |
| `ignoreIn` | longer phrases that contain an alias but name something else |

The tag name is not matched on its own: every spelling, including the tag name, has to be listed
under `aliases` or `caseSensitive`. `load_dictionary()` rejects a file with a duplicate tag or an
entry with no spelling at all.

Categories: ai-ml, backup-storage, business-apps, cloud, collaboration, compliance, data,
database, devops, endpoint-mgmt, frameworks, identity, itsm, languages, networking,
observability, os, rmm-msp, security, virtualization.

## Choices worth knowing about

- Bare `Go` is not a spelling (it would match "Go-to-market" and "go"). Only `Golang` and
  `Go (Golang)` tag Go, so posts that say "Python or Go" are missed. That trade-off is on purpose.
- Bare `Windows` is not a tag; Windows Server and the Microsoft tools are.
- `Slack`, `Zoom`, `Microsoft Teams` / `MS Teams` and `Webex` are gated because job posts mention
  them in culture lines ("coffee chats and Slack conversations").

## Adding a tool

Add an entry next to the others in its category, and add a test in `tests/test_tagger.py`
that shows one post it should match and one it should not. For one-off terms you can skip the
file: `jobstack tag --term 'Kolide=Kolide|1Password XAM'` or `Tagger.add_terms([...])`.

---
title: "Notes"
nav_order: 17
summary: "Where notes live, what their front matter must say, and how they are built and checked."
status: stable
---

# Notes

Notes are dated articles served at `guardana.dev/notes/`. Each one is a markdown file
`notes/<slug>.md` at the repository root. The file name is the URL: the slug is lowercase
words joined by hyphens, and `index` is reserved. `notes/` holds nothing else. A
subdirectory, or any file that is not `<slug>.md`, fails the build.

| key | required | check |
|---|---|---|
| `title` | yes | plain text, no link or image, unique across notes |
| `date` | yes | an ISO date, `YYYY-MM-DD`, without a time |
| `summary` | yes | text; inline code allowed, no link or image |
| `devto` | no | the `https://dev.to/` URL of the cross-post, shown as "Also on dev.to" |

Any other key, a missing closing `---` line or an empty body fails the build, and the error
names the file. No title or summary may hold a control character.

The body is rendered like a documentation page, diagrams and tables included, with
three limits:

- A local link must point at a published page under `docs/` or another note. It is
  rewritten to its served URL, and its anchor must exist. Any other repository file is
  linked by its full URL.
- A note embeds no image.
- Every `guardana` command line in a note is checked against the real command tree by
  [`test_documented_commands_exist.py`](../../packages/guardana-cli/tests/test_documented_commands_exist.py).

With no note, nothing is built and no page links to the notes. With at least one, the build
writes `site/notes/index.html`, one page per note and the Atom feed `site/notes/feed.xml`.
The documentation header gains a Notes link, and the sitemap and `llms.txt` list the notes.

```bash
uv run python scripts/build_site.py
uv run python scripts/generate_llms_txt.py
uv run python scripts/generate_sitemap.py
uv run python scripts/build_site.py --check
uv run python scripts/generate_sitemap.py --check
```

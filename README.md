# atlantide-org.github.io

The documentation site for [Atlantide](https://github.com/atlantide-org/atlantide),
built with MkDocs and Material, and published to <https://atlantide-org.github.io/>.

## Building

```bash
make docs-serve      # http://127.0.0.1:8000/
make docs            # build once into site/, --strict
```

`--strict` is what CI runs. Link and anchor validation are on, so a dead
cross-reference or a page missing from the nav fails the build rather than
shipping a 404 — worth knowing, because the How it works pages are heavily
cross-linked and their headings carry numbers.

## Layout

| Path | What it is |
|---|---|
| `docs/` | The pages. Each starts with a `description:` in its front matter, used for the page's meta tag and its line in `llms.txt`. |
| `agents/SKILL.md` | The guide for coding agents. Single source: the For agents page includes it, and the build publishes it. |
| `scripts/llms.py` | MkDocs hook that writes the machine-readable side of the site (below). |
| `overrides/` | Material template overrides: the Markdown link and copy button on every page, and `<link rel="alternate">` in the head. |

## The machine-readable side

After the HTML, `scripts/llms.py` writes into `site/`:

- `<page>.md` beside every page — its Markdown, with admonitions, tabs, card
  grids and icons flattened to plain Markdown and every link made absolute;
- `llms.txt` — an [llms.txt](https://llmstxt.org) index of those, in nav order,
  using each page's `description`;
- `llms-full.txt` — every page in one file;
- `agents/SKILL.md` and `agents/AGENTS.md` — the agent guide, with and without
  Claude Code skill frontmatter.

A new page needs a nav entry and a `description`. Pages that are background
rather than needed to write a config are listed under `OPTIONAL` in the hook,
which puts them in the llms.txt section agents may skip.

When the engine changes behaviour an agent relies on — a command, a flag, a
rejected construct, an error name — update `agents/SKILL.md` along with the
page that documents it.

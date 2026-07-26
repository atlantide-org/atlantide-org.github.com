"""MkDocs hook: the machine-readable side of the site.

After the HTML is built, this writes:

- ``/<page>.md`` beside every page: the page's Markdown, with site-only syntax
  (admonitions, content tabs, card grids, icons, snippet includes) flattened to
  plain Markdown and every relative link made absolute.
- ``/llms.txt``: an index of those files in nav order, per https://llmstxt.org.
- ``/llms-full.txt``: every page concatenated, for a single fetch.
- ``/agents/SKILL.md`` and ``/agents/AGENTS.md``: the drop-in agent guide.

Everything is derived from the same sources as the HTML, so the two views of
the site cannot disagree.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import Any

from mkdocs.structure.nav import Navigation, Section
from mkdocs.structure.pages import Page

AGENTS_DIR = Path("agents")

_pages: dict[str, tuple[Page, str]] = {}
_nav: Navigation | None = None

# One-paragraph context an agent needs before reading anything else.
SUMMARY = """\
Atlantide is a typed, deterministic Infrastructure-as-Code engine for Python.
Configs are ordinary Python files (`infra.py`) executed by Atlas-lang, a bounded
interpreter with no clock, randomness, environment, network or filesystem, so
the same config always produces the same plan. Resources form a Merkle-hashed
dependency graph; apply skips any node whose hash is unchanged without calling
the provider."""

AGENT_NOTES = """\
Notes for agents:

- Each page below is plain Markdown. Append `.md` to any page's path, or use the
  links here. `llms-full.txt` is every page in one file.
- Before writing a config, read the agent guide (`agents/SKILL.md`): it lists
  the Atlas-lang restrictions and the validate/plan loop to follow.
- Discover types from the installed CLI rather than from memory:
  `atlantide resources` and `atlantide schema <type>`.
- `atlantide validate` and `atlantide plan` need no credentials and change
  nothing. `apply`, `destroy`, `deploy` and `state` subcommands change real
  infrastructure or its record; do not run them without the user's approval."""

# Pages that are background rather than needed to write a config.
OPTIONAL = {"how-it-works/walkthrough.md", "how-it-works/merkle.md",
            "how-it-works/failure.md", "glossary.md", "comparison.md"}

_ADMONITION = re.compile(r'^(?:!!!|\?\?\?\+?)\s+(\w+)(?:\s+"([^"]*)")?\s*$')
_TAB = re.compile(r'^===\+?\s+"([^"]*)"\s*$')
_SNIPPET = re.compile(r'^(\s*)--8<--\s+"([^"]+)"\s*$')
_LINK = re.compile(r"(\]\()([^)\s]+)(\))")
_ICON = re.compile(r":(?:material|octicons|fontawesome|simple)-[a-z0-9-]+:\s*")
_ATTRS = re.compile(r"\s*\{\s*[.#:][^}\n]*\}")
_DIV = re.compile(r"^\s*</?div\b[^>]*>\s*$")


def on_nav(nav: Navigation, config: Any, files: Any) -> Navigation:
    global _nav
    _nav = nav
    return nav


def on_page_markdown(markdown: str, page: Page, config: Any, files: Any) -> str:
    _pages[page.file.src_uri] = (page, markdown)
    return markdown


def on_post_build(config: Any) -> None:
    site = Path(config["site_dir"])
    base = config["site_url"]
    ordered = _ordered_pages()

    rendered: dict[str, str] = {}
    for src, (page, markdown) in _pages.items():
        text = _to_plain(markdown, src, base)
        rendered[src] = text
        out = site / src
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

    (site / "llms.txt").write_text(_index(ordered, base), encoding="utf-8")

    full = [f"# {config['site_name']}\n\n> {config['site_description']}\n\n{SUMMARY}\n"]
    for section, src in ordered:
        full.append(f"\n\n<!-- source: {base}{src} -->\n\n{rendered[src].strip()}\n")
    (site / "llms-full.txt").write_text("".join(full), encoding="utf-8")

    skill = (AGENTS_DIR / "SKILL.md").read_text(encoding="utf-8")
    (site / "agents").mkdir(exist_ok=True)
    (site / "agents" / "SKILL.md").write_text(skill, encoding="utf-8")
    (site / "agents" / "AGENTS.md").write_text(_strip_frontmatter(skill), encoding="utf-8")


def _ordered_pages() -> list[tuple[str | None, str]]:
    """(section title, src_uri) for every page, in nav order."""
    out: list[tuple[str | None, str]] = []

    def walk(items: list[Any], section: str | None) -> None:
        for item in items:
            if isinstance(item, Section):
                walk(item.children, item.title)
            elif isinstance(item, Page) and item.file.src_uri in _pages:
                out.append((section, item.file.src_uri))

    assert _nav is not None
    walk(_nav.items, None)
    return out


def _index(ordered: list[tuple[str | None, str]], base: str) -> str:
    lines = [f"# Atlantide\n\n> {SUMMARY.replace(chr(10), ' ')}\n\n{AGENT_NOTES}\n"]
    lines.append("\n## Agent guide\n\n"
                 f"- [SKILL.md]({base}agents/SKILL.md): rules, idioms and the "
                 "validate/plan loop for writing Atlantide configs. Also served "
                 f"without frontmatter as [AGENTS.md]({base}agents/AGENTS.md).\n")

    # Nav order, with a top-level page heading its own group. llms.txt reserves
    # "Optional" for what a reader may skip, so those pages are collected last.
    groups: dict[str, list[str]] = {}
    for section, src in ordered:
        page, _ = _pages[src]
        key = "Optional" if src in OPTIONAL else (section or page.title)
        desc = page.meta.get("description", "")
        entry = f"- [{page.title}]({base}{src})" + (f": {desc}" if desc else "")
        groups.setdefault(key, []).append(entry)

    for key in sorted(groups, key=lambda k: k == "Optional"):
        lines.append(f"\n## {key}\n\n" + "\n".join(groups[key]) + "\n")
    lines.append(f"\n## Everything\n\n- [llms-full.txt]({base}llms-full.txt): "
                 "all of the above in one file.\n")
    return "".join(lines)


def _to_plain(markdown: str, src: str, base: str) -> str:
    text = _flatten(_include_snippets(markdown).splitlines())
    text = _ICON.sub("", text)
    text = _ATTRS.sub("", text)
    text = "\n".join(line for line in text.splitlines() if not _DIV.match(line))
    text = _LINK.sub(lambda m: m[1] + _absolute(m[2], src, base) + m[3], text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _include_snippets(markdown: str) -> str:
    def repl(m: re.Match[str]) -> str:
        body = (AGENTS_DIR / m[2]).read_text(encoding="utf-8").rstrip("\n")
        return "\n".join(m[1] + line if line else line for line in body.splitlines())

    return "\n".join(_SNIPPET.sub(repl, line) for line in markdown.splitlines())


def _flatten(lines: list[str]) -> str:
    """Admonitions become blockquotes and content tabs become labelled blocks.

    Both are recognised only outside fenced code, and their bodies (the
    following lines indented by four spaces) are flattened recursively, so a
    tab holding an admonition comes out right.
    """
    out: list[str] = []
    fence: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if fence is None and stripped.startswith(("```", "~~~")):
            fence = stripped[: len(stripped) - len(stripped.lstrip(stripped[0]))]
        elif fence is not None and stripped.startswith(fence) and not stripped[len(fence):].strip():
            fence = None
        elif fence is None and (m := _ADMONITION.match(line) or _TAB.match(line)):
            body, i = _block(lines, i + 1)
            inner = _flatten(body)
            if line.startswith("==="):
                out += [f"**{m[1]}**", "", inner, ""]
            else:
                title = m[2] if m.lastindex and m.lastindex >= 2 and m[2] else m[1].capitalize()
                out += [f"> **{title}**", ">"]
                out += [f"> {l}".rstrip() for l in inner.splitlines()] + [""]
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _block(lines: list[str], i: int) -> tuple[list[str], int]:
    body: list[str] = []
    while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
        body.append(lines[i][4:])
        i += 1
    while body and not body[-1].strip():
        body.pop()
    return body, i


def _absolute(target: str, src: str, base: str) -> str:
    if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
        return target
    path, _, anchor = target.partition("#")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(src), path))
    return base + resolved + (f"#{anchor}" if anchor else "")


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5:].lstrip()
    return text

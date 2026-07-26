---
description: "Machine-readable docs (llms.txt, per-page Markdown) and a drop-in skill that teaches coding agents to write and plan Atlantide configs safely."
---

# For agents

Every page on this site is also published as plain Markdown for coding agents,
along with a short guide for agents that edit a config.

## Give your agent the guide

[`SKILL.md`](https://atlantide-org.github.io/agents/SKILL.md) covers the
Atlas-lang restrictions, how dependencies and `Ref`s work, the `validate` →
`plan` loop, which commands are safe to run unasked, and what each error means. It is reproduced
[below](#the-guide).

=== "Claude Code"

    Install it as a project skill; Claude Code loads it whenever a task touches
    the config:

    ```bash
    mkdir -p .claude/skills/atlantide
    curl -fsSL https://atlantide-org.github.io/agents/SKILL.md \
      -o .claude/skills/atlantide/SKILL.md
    ```

=== "AGENTS.md"

    For Codex, Cursor, Copilot, Aider and anything else that reads `AGENTS.md`,
    append the same guide without its frontmatter:

    ```bash
    curl -fsSL https://atlantide-org.github.io/agents/AGENTS.md >> AGENTS.md
    ```

=== "Anything else"

    Paste the guide into the system prompt, or point the agent at
    `https://atlantide-org.github.io/llms.txt` and let it follow the links.

Commit the file with the project so every contributor's agent uses the same
rules.

## Machine-readable docs

| URL | What it is |
|---|---|
| [`/llms.txt`](https://atlantide-org.github.io/llms.txt) | An index of every page as Markdown, with a one-line description each, in the [llms.txt](https://llmstxt.org) format. |
| [`/llms-full.txt`](https://atlantide-org.github.io/llms-full.txt) | Every page in one file, in navigation order. |
| `/<page>.md` | Any single page: replace the trailing `/` of its URL with `.md`, e.g. [`/reference/cli.md`](https://atlantide-org.github.io/reference/cli.md). |
| [`/agents/SKILL.md`](https://atlantide-org.github.io/agents/SKILL.md) | The guide, with Claude Code skill frontmatter. |
| [`/agents/AGENTS.md`](https://atlantide-org.github.io/agents/AGENTS.md) | The same guide, without it. |

The Markdown versions are generated from the same sources as these pages, with
admonitions turned into blockquotes, tabs into labelled blocks, and every link
made absolute. Each page also advertises its Markdown with
`<link rel="alternate" type="text/markdown">`, and the buttons at the top right
of every page view it or copy it to the clipboard.

## Let the CLI answer

The installed CLI reports the resource types and schemas available in that
install. The guide tells agents to query it:

```bash
atlantide resources              # every resource type this install can see
atlantide schema aws.S3Bucket    # one type's fields, mutability and defaults
atlantide validate --json        # compile, with a machine-readable result
atlantide plan --json --detailed-exitcode
```

`--json` output and exit codes are covered under
[CI and automation](reference/ci.md).

## The guide

````markdown
--8<-- "SKILL.md"
````

---
description: "Running atlantide unattended: pre-commit validation, plan as a pull-request gate, apply on merge, build-once promotion, JSON output and exit codes."
---

# CI and automation

The first half of the pipeline performs no I/O, so per-commit checks need no
provider credentials. A typical setup validates on every commit, plans on pull
requests, and applies on merge.

| Stage | Command | Needs |
|---|---|---|
| pre-commit | `atlantide validate` | nothing |
| pull request | `atlantide plan --detailed-exitcode` | read access to state |
| merge to main | `atlantide apply -y` | provider credentials, write access to state |

## Validate in a pre-commit hook

`validate` checks that the config stays within the Atlas-lang subset and that
its graph is acyclic. It touches no state and calls no provider:

```yaml title=".pre-commit-config.yaml"
repos:
  - repo: local
    hooks:
      - id: atlantide-validate
        name: atlantide validate
        entry: atlantide validate
        language: system
        pass_filenames: false
        files: ^(infra\.py|atlantide\.toml)$
```

## Plan as a pull-request gate

Without `--detailed-exitcode`, a plan with pending changes and a plan with none
both exit `0`. With it:

| Code | Meaning |
|---|---|
| `0` | No changes. |
| `1` | An error, or a mandatory [policy](policies.md) denied the plan. |
| `2` | Changes pending. |

A policy denial exits `1` in both modes, so it is distinct from pending changes.

## Apply on merge

A mutating command in CI needs `-y` to skip the confirmation prompt. Also
configure:

- **Concurrency.** Two applies over the same stack serialize on the state
  lease; see [Concurrency](remote-state.md#concurrency). Queue deploys per
  state backend rather than cancelling one mid-run.
- **Failure policy.** `--on-failure rollback` (the default) undoes the nodes a
  failed run completed; `halt` leaves them for a human. See
  [When apply fails](../how-it-works/failure.md).

## GitHub Actions

```yaml title=".github/workflows/infra.yml"
name: Infrastructure

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write          # for OIDC to AWS

concurrency:
  group: infra-${{ github.ref }}
  cancel-in-progress: false  # never cancel an apply half-way

jobs:
  infra:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv tool install atlantide

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.ATLANTIDE_ROLE_ARN }}
          aws-region: eu-north-1

      - run: atlantide validate

      - name: Plan
        if: github.event_name == 'pull_request'
        run: |
          set +e
          atlantide plan --detailed-exitcode
          code=$?
          [ "$code" -eq 2 ] && echo "::notice::changes pending"
          [ "$code" -eq 1 ] && exit 1
          exit 0

      - name: Apply
        if: github.ref == 'refs/heads/main'
        run: atlantide --audit-log audit.jsonl apply -y
```

This requires a shared [state backend](remote-state.md) in `atlantide.toml`;
the default local SQLite file does not persist between CI runs. If the config
imports a third-party provider, install it into the same environment
(`uv tool install atlantide --with acme-atlantide`); the
[standalone binary](../install.md#provider-plugins-and-the-binary) cannot load
plugins.

## Build once, deploy the same bytes

`build` compiles the config into a content-hashed `.atlas` artifact with
provider versions pinned. `deploy` applies an artifact without executing the
config again, so production receives the same bytes that were tested in
staging:

```bash
atlantide build -o release.atlas              # in the build job
atlantide verify release.atlas                # hash check, anywhere
atlantide -P staging deploy release.atlas -y  # then, unchanged:
atlantide -P prod    deploy release.atlas -y
```

`--env` given to `build` is recorded in the artifact, so a `deploy` covers the
same environments the build did.

## Machine-readable output

`--json` replaces the rendered output with a JSON document on stdout. It is
accepted by `plan`, `apply`, `validate`, `refresh`, `import`, `init`, `output`,
`providers`, `state list` and `state show`. Every payload from a command that
touches state carries a `state` field naming the backend it used.

```bash
atlantide plan --json > plan.json
atlantide output --json
```

Logging is separate from command output and goes to stderr. The options are
global, so they come **before** the command:

```bash
atlantide --log-level info --log-format json plan
atlantide --audit-log audit.jsonl apply -y       # append every event to a JSONL file
```

| Global option | Environment variable |
|---|---|
| `--profile/-P` | `ATLANTIDE_PROFILE` |
| `--log-level` | `ATLANTIDE_LOG_LEVEL` |
| `--audit-log` | `ATLANTIDE_AUDIT_LOG` |
| `--debug` | — |
| `--no-plugins` | — |

The Postgres backend also reads its DSN from `ATLANTIDE_STATE_DSN`, which keeps
the password out of `atlantide.toml`.

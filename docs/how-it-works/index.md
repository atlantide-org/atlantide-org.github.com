---
description: "The engine's mental model, the eight-stage pipeline on one page, and which command runs which stages."
---

# How it works

This section describes the engine in three levels of detail.

- **This page** — the mental model, the pipeline, and which command runs which
  stages.
- **[Walkthrough](walkthrough.md)** — the pipeline run end to end against local
  files. It needs no credentials or AWS account.
- **[The Merkle hash](merkle.md)** — how `input_hash` is computed and used, with
  real numbers.
- **[When apply fails](failure.md)** — the apply phases, what is rolled back,
  what cannot be, and how a failed rollback is kept visible.

The [glossary](../glossary.md) defines every term below, in pipeline order.

---

## The mental model

Atlantide runs a Python file in a sandbox with no clock, randomness, environment
or network. The resources the file creates become a content-hashed dependency
graph, the IR.

Each node is hashed together with its dependencies, producing an `input_hash`
per node. These hashes are compared against those recorded in a state database;
the difference between the two sets is the plan.

Apply walks the graph in topological order, in parallel, and calls providers
only for nodes whose hash changed.

This has two consequences:

**`plan` needs no credentials.** Everything up to the diff is pure computation
over the config and the recorded state.

**The diff compares desired inputs against recorded inputs, not against the live
world.** Detecting infrastructure changed outside Atlantide is a separate
command, `refresh`. The
[walkthrough](walkthrough.md#11-drift-and-the-limit-of-the-model) shows where
that boundary sits and what it costs.

---

## The whole pipeline on one page

```
infra.py
   │
   │  ─── pure: no I/O, no credentials, byte-reproducible ───
   │
   ├─ 1  Atlas-lang        validate_source + Interpreter.run   lang/validate.py, lang/interp.py
   ├─ 2  Lower             lower(registry, providers)          ir/lower.py
   ├─ 3  Canonicalize      RFC 8785 + sha256                   ir/hash.py
   ├─ 4  Graph             build_graph (Tarjan) + Kahn         graph/build.py, graph/order.py
   ├─ 5  Merkle            merkle_hashes -> input_hash/node    ir/merkle.py
   │
   │  ─── touches the world ───
   │
   ├─ 6  Diff              vs prior hashes from state          reconcile/diff.py
   ├─ 7  Plan              guard + policies                    reconcile/planner.py, engine/planner.py
   └─ 8  Apply             lease -> re-diff -> parallel DAG    engine/locking.py, reconcile/executor.py
```

The layering is enforced.
[`pyproject.toml`](https://github.com/atlantide-org/atlantide/blob/main/pyproject.toml)
declares import-linter contracts for the order
`cli > engine > reconcile > (policy | providers | state | secrets | lang) > graph > ir > core`,
plus three rules: `core` imports no sibling package, and `providers` and
`secrets` depend only on `core`.

The contracts run in CI with `mypy --strict` and a 90% coverage floor. An import
that crosses a layer sideways fails the build.

---

## Command reference

| Command | Runs stages | Needs credentials | Writes state |
|---|---|---|---|
| `validate` | 1–5 | no | no |
| `graph` | 1–4 | no | no |
| `build` | 1–5 | no | no |
| `verify` | — | no | no |
| `plan` | 1–7 | no | no |
| `apply` | 1–8 | yes | yes |
| `deploy` | 6–8 (from artifact) | yes | yes |
| `refresh` | provider `read` only | yes | only with `--write` |
| `import` | 1–5, then provider `read` only | yes | yes (records; creates nothing) |
| `destroy` | 6–8, empty desired graph | yes | yes |
| `init` | — (compiles the config it scaffolds) | no | no |

The mutating commands share a set of flags: `--confirm/-y`, `--state`,
`--region`, `--parallelism/-p`, `--on-failure rollback|halt` (defaulting to
`rollback`), `--target/-t` and `--replace`. `--audit-log` is a global option,
given before the command. `--on-failure` is described in
[When apply fails](failure.md).

`--env/-e` narrows a run to named environments of the config's
[`Config`](../reference/configuration.md#environments). `plan`, `apply`,
`validate`, `build` and `destroy` take it; `refresh` does not.

Defaults come from `atlantide.toml`, looked up from the current directory
upwards. It sets the config path, the state backend, the secrets
provider, parallelism, AWS region, profile and endpoint, component pins, inputs,
and any `[profile.<name>]` overlays selected with `-P`. See
[Configuration](../reference/configuration.md).

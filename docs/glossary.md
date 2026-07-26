---
description: "Every Atlantide term — Atlas-lang, Ref, input_hash, changeset, lease, compensation — defined in pipeline order."
---

# Glossary

Terms used across these pages, in the order the pipeline meets them.

**Atlas-lang** — the bounded interpreter that executes a config. Python syntax,
without any construct that would let the result depend on anything other than
the config text and its declared inputs: no clock, randomness, environment,
network or filesystem. See
[what config may not do](reference/authoring.md#what-config-may-not-do).

**Fuel** — the step budget for an evaluation. A runaway computation stops with
a `FuelExhaustedError` instead of hanging.

**Input** — a per-run value the config may branch on, supplied by `-var`,
`--var-file` or `[inputs]`. The determinism guarantee is over *(config, inputs,
selected environments)*, not config alone. Not for secrets.

**Config** — the checked-in environment matrix: every environment and what
differs between them, declared once as `Config(AppEnv, envs={...})` and validated
on construction. An input, by contrast, is a per-run value from outside the
repository. See
[Environments](reference/configuration.md#environments).

**`EnvSchema`** — the shape of one environment, declared as a class of annotated
fields. It is the only class Atlas-lang admits, because it is a declaration, not a
computation. It makes `env.domain` complete in an editor and `env.domian` a type
error. The untyped alternative is a mapping of `var()` declarations.

**Environment** — one entry in a `Config`. Its name is its stack's name, and
`--env` narrows a run to it. An environment left out is *out of scope*, not
undeclared: its state is not diffed and is never planned for deletion.

**Resource** — one managed thing, declared with a logical name. Its fields carry
their own mutability.

**Logical name** — the name you give a resource in config. **Node id** — what it
becomes once scoped: `{stack}:{type}:{name}`, e.g. `prod:aws.S3Bucket:assets`.
Most commands accept a short form or a glob in place of a full id.

**Stack** — a namespace scoping region, tags and name prefix over the resources
declared in its body.

**Component** — several resources behind one parameterized object. Written in
Python, used by config, never defined by it. The children become ordinary flat
resources named `{component}-{child}`.

**Ref** — the lazy handle returned by reading a computed field. The read creates
the dependency edge; the `Ref` resolves to a real value at apply.

**Mutability** — each field is `mutable()` (in-place `UPDATE`), `immutable()`
(`REPLACE`) or `computed()` (never diffs; produced by the provider).

**IR** — the intermediate representation: the content-hashed, provider-stamped
graph a config lowers to. Everything downstream works on the IR, not on the
source.

**Canonical form** — RFC 8785 JSON. Fixes key order, number formatting and
string escaping, so the same IR always serializes to the same bytes and the
content hash is stable.

**`input_hash`** — a node's Merkle hash: its own canonical inputs folded
together with its dependencies' hashes. Unchanged hash, no provider call. See
[The Merkle hash](how-it-works/merkle.md).

**Symbolic ref** — the hash is computed over the *reference* to an upstream
value, not over the resolved value (which does not exist yet at plan time).

**Diff** — the comparison of desired `input_hash`es against those recorded in
state. It compares against *recorded* inputs, not the live world; comparing
against the live world is [`refresh`](reference/cli.md#detecting-drift).

**Changeset** — the result: one action per node — `NOOP`, `CREATE`, `UPDATE`,
`REPLACE` or `DELETE`.

**Conditional replace** — a `REPLACE` caused by an immutable field holding a
`Ref`. It becomes a no-op if the value resolves unchanged at apply.

**Plan** — the ordered, guarded, policy-checked changeset.

**Policy** — a check over one node's pending change, evaluated at plan time.
`MANDATORY` blocks, `ADVISORY` warns. See [Policies](reference/policies.md).

**Lease / lock** — the time-bounded claim a run takes on state before writing.
Renewed while the run lives; lapses if it dies.

**Fenced write** — a state write that succeeds only if the writer is still the
recorded lease holder. The store makes the check, not the writer, which prevents
two concurrent runs from silently merging state.

**Compensation** — the undo recorded for a completed node, run in reverse
completion order when an apply fails. See [When apply
fails](how-it-works/failure.md).

**Poisoned row** — a state row whose `input_hash` is cleared so the next plan
cannot Merkle-skip it. Set before a compensation runs, so a rollback that fails
mid-way cannot leave a silent divergence.

**Plan drift** — the changeset about to execute differs from the one that was
approved, because state moved between the two. Raised, not reconciled.

**Drift** — the live world differing from what state records. Found by
`refresh`, and only in the fields a provider's `read` reports.

**Artifact** (`.atlas`) — a compiled, content-hashed config with provider
versions pinned. `deploy` applies it without re-executing the config, so identical
bytes are promoted between environments.

**Output** — a value exported with `output()`, namespaced by its stack and
persisted into state after apply. Read back with `atlantide output`, or from
another stack via `StackReference`.

**Secret** — a name, not a value. `atlantide.secret("x")` returns a `SecretRef`;
the plaintext is resolved in-memory at apply and never reaches the IR, the
artifact or state.

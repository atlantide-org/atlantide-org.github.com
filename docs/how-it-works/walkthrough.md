---
description: "The pipeline run end to end against local files, no credentials needed: IR, hashes, diff, apply, skip, drift."
---

# Walkthrough

This page runs the whole pipeline without credentials. Every command below was
run, and every output block is the output it produced.

The example uses the `local` provider, which writes files to disk, so no AWS
account is needed. The pipeline is the same one the AWS provider uses; only the
`create`, `read`, `update` and `delete` implementations differ.

This page assumes the [mental model](index.md#the-mental-model).

---

## 1. Set up the example

```bash
mkdir demo && cd demo
```

`demo/infra.py`:

```python
"""A two-resource walkthrough config, credentials-free."""

from atlantide.core import Stack, output
from atlantide.providers.local import File

with Stack("demo", region="eu-north-1"):
    greeting = File("greeting", path="out/greeting.txt", content="hello atlantide")

    # Reading `greeting.checksum` returns a lazy Ref -> a real dependency edge.
    File("receipt", path="out/receipt.txt", content=greeting.checksum)

output("greeting_checksum", greeting.checksum)
```

The config has three parts:

| Line | What it is |
|---|---|
| `with Stack("demo", region=...)` | A namespace. Every resource inside gets node id `demo:<type>:<name>`. `region` is required even for the local provider — it is stack metadata, not a provider detail. |
| `greeting.checksum` | `checksum` is a `computed()` field — its value does not exist yet. Reading it returns a lazy `Ref` ([`core/types.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/core/types.py)), which is what creates the dependency edge. No `depends_on`, no string addresses. |
| `output(...)` | A declared output, persisted into state after apply. Declared *outside* the `with` block here, so it lands in the `default` namespace (`default:greeting_checksum`). Move it inside the block and it becomes `demo:greeting_checksum` and is readable by another stack. |

`File` itself declares its per-field mutability
([`providers/local/resources.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/providers/local/resources.py)):

```python
class File(LocalResource):
    path: str = immutable()      # changing it => REPLACE
    content: str = mutable(default="")   # changing it => in-place UPDATE
    checksum: str = computed()   # never diffs; produced by the provider
```

This declaration tells the engine that a path change requires a recreate and a
content change does not. The cost is visible in the type before anything runs.

---

## 2. Validate — the pure front half, on its own

```bash
atlantide validate infra.py
```

```
ok infra.py — 2 resource(s), no cycles
```

It uses no state file, credentials or network access, which makes it suitable
for a pre-commit hook. It runs pipeline stages 1–5 (sections 3–6 below) and stops.

### The sandbox is real, not a convention

```bash
# a while loop
atlantide validate bad.py
```
```
error: construct 'While' is not allowed in Atlas-lang — Atlas-lang has no
`while` (halting must be provable); use a bounded `for`. (line 2, col 0)
   2 | while True:
       ^
```

```bash
# import os
atlantide validate bad.py
```
```
error: import of 'os' is not allowed (only 'atlantide.core', '.policy',
'.providers.*', '.components.*') — config must be a pure function of its inputs;
move helpers into a provider or use Atlas builtins (`uuid5`, `sha256_hex`,
`to_json`, `merge`, `slugify`). (line 1, col 0)
   1 | import os
       ^
```

Also rejected: `class`, `try`, dunder access, `eval`, `str.format`, and attribute
assignment such as `a.content = ...`. (The single `class` exception is an
[`EnvSchema`](../reference/configuration.md#the-schema) declaring an
environment's fields — annotated names only, no methods, so it is data.)

Because of the last restriction, a dependency cycle is close to unwritable:
references can only be wired at construction time, and construction is ordered.

---

## 3. Stage 1 — Atlas-lang: subset check, then bounded evaluation

**Code trace**

```
Engine.compile()                          engine/engine.py
  └─ evaluate_source()                    lang/__init__.py
       ├─ build_globals(inputs)           lang/builtins.py # safe builtins + uuid5, sha256_hex, to_json, merge, slugify
       ├─ validate_source()               lang/validate.py # ast walk; rejects the constructs above
       └─ _run_module()                   lang/__init__.py
            ├─ collecting()               core/resource.py # a context that captures every Resource constructed
            └─ Interpreter(fuel=...).run  lang/interp.py   # tree-walking, fuel-bounded
```

It is a **tree-walking interpreter**, not `exec`. The interpreter never binds an
`os` module.

Evaluation is **fuel-bounded**: a step budget prevents a config from hanging the
engine. With the ban on `while`, this makes termination provable.

Every exception that is not already an `AtlantideError` is converted to a
`LanguageError`, so a broken config produces a configuration error rather than
an engine stack trace.

Output: a `ResourceRegistry` ([`core/resource.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/core/resource.py))
  holding the resources, the declared outputs, the policy bindings and the inputs
  the config read.

---

## 4. Stage 2 — Lowering to IR

```
Engine._compile_registry()                engine/engine.py
  ├─ inline_stack_outputs(registry)       core/inline.py # fold in-config cross-stack refs into real Ref edges
  └─ lower(registry, providers)           ir/lower.py
```

Each `Resource` becomes an `IRNode` ([`ir/model.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/ir/model.py)):
canonical inputs, the dependency ids taken from `resource.refs()`, and the
provider name **and version** stamped in.

`build` writes the IR to a file (step 12):

```json
{
  "nodes": [
    {
      "dependencies": [],
      "id": "demo:local.File:greeting",
      "properties": {
        "content": "hello world",
        "path": "out/greeting.txt"
      },
      "provider": "local",
      "provider_version": "1.0.0",
      "type": "local.File"
    },
    {
      "dependencies": [
        "demo:local.File:greeting"
      ],
      "id": "demo:local.File:receipt",
      "properties": {
        "content": {
          "$ref": "demo:local.File:greeting#checksum"
        },
        "path": "out/receipt.txt"
      },
      "provider": "local",
      "provider_version": "1.0.0",
      "type": "local.File"
    }
  ],
  "version": 1
}
```

`greeting.checksum` had no value at config time; it is now the data
`{"$ref": "demo:local.File:greeting#checksum"}`, and `dependencies` records the
edge it implies. The lazy attribute read has become a serialisable graph edge.

---

## 5. Stage 3 — Canonicalize and hash

```
canonical_bytes()   ir/hash.py   # RFC 8785 JSON Canonicalization Scheme
hash_ir()           ir/hash.py   # sha256 over those bytes
```

RFC 8785 fixes key order, number formatting and string escaping, so the same IR
always serialises to the same bytes. This makes the content hash stable and the
`.atlas` artifact portable.

To verify, build twice and compare:

```bash
atlantide build infra.py -o a.atlas
atlantide build infra.py -o b.atlas
shasum -a 256 a.atlas b.atlas
```

```
built a.atlas — 2 nodes, hash f9ecb89e5ade…, pins {'local': '1.0.0'}
built b.atlas — 2 nodes, hash f9ecb89e5ade…, pins {'local': '1.0.0'}
6f10115bf10968dfda4081c19041a92183081875ee1f6370f2f8fbed9ba2292c  a.atlas
6f10115bf10968dfda4081c19041a92183081875ee1f6370f2f8fbed9ba2292c  b.atlas
```

The files are byte-identical, not only their hashes.

---

## 6. Stages 4–5 — Graph and Merkle

```
assemble_compiled()          engine/hydrate.py
  ├─ build_graph(ir)         graph/build.py # DiGraph; cycles rejected (iterative Tarjan)
  ├─ topological_order(g)    graph/order.py # Kahn
  └─ merkle_hashes(ir, topo) ir/merkle.py   # input_hash per node
```

Inspect the graph without applying anything:

```bash
atlantide graph infra.py --format mermaid
```

```
graph LR
  subgraph cluster0["demo"]
    n0["local.File:greeting"]
    n1["local.File:receipt"]
  end
  n0 --> n1
```

The result of all four pure stages is a `Compiled`
([`engine/model.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/engine/model.py)): IR, graph,
hashes, resources, policy bindings, outputs, inputs.

Every later stage depends on the `input_hash` computed here.
[The Merkle hash](merkle.md) covers its definition, how a change propagates, and
the two cases the hash cannot see.

---

## 7. Stages 6–7 — Diff and Plan

```bash
atlantide plan infra.py --state demo.db
```

```
state: demo.db
demo ───────────────────────────────────────────────────────────────────────────
  + create  local.File:greeting
  + create  local.File:receipt

Plan: 2 to add

Outputs:
  default:greeting_checksum = (known after apply)
```

**Code trace**

```
Engine.plan()                        engine/engine.py
  └─ _plan_from_compiled()           engine/engine.py
       ├─ resolve_aliases(backend.load(), ir)   reconcile/aliases.py # a rename maps onto the existing row, not destroy+create
       ├─ _selection(...)            engine/engine.py                # --target / --replace, closed over dependencies
       └─ Planner.build()            engine/planner.py
            ├─ diff(ir, hashes, prior, mutability)   reconcile/diff.py
            ├─ force_replace(...)    reconcile/diff.py               # --replace
            ├─ restrict(...)         reconcile/diff.py               # --target
            ├─ plan(raw, protected)  reconcile/planner.py            # prevent_destroy guard — AFTER the two above
            └─ _refine()             engine/planner.py
                 ├─ _audit_secrets / _require_secrets
                 ├─ _require_stack_outputs
                 └─ _finalize -> _resolve_cbd + _evaluate_policies
```

The diff compares the desired `input_hash` against the `input_hash` stored on the
prior state node. State is empty here, so both nodes are creates. When a hash
differs,
[`_classify`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/reconcile/diff.py)
uses the per-field mutability map to choose between an update and a
replacement.

Policies run at the end of planning, against the finished changeset. A mandatory
violation sets `Plan.blocked`, and `apply` refuses before touching anything.

Machine-readable form for CI:

```bash
atlantide plan infra.py --state demo.db --json
```
```json
{
    "schema_version": 1,
    "ok": true,
    "summary": { "create": 0, "update": 0, "replace": 0, "delete": 0, "noop": 2 },
    "inputs": {},
    "changes": [
        {
            "node_id": "demo:local.File:greeting",
            "action": "noop",
            "changed_fields": [],
            "conditional": false,
            "create_before_destroy": false
        }
    ],
    "outputs": { "default:greeting_checksum": null },
    "violations": [],
    "warnings": [],
    "blocked": false,
    "state": "demo.db"
}
```

`--detailed-exitcode` returns `0` for no changes, `2` for changes pending and
`1` for an error.

---

## 8. Stage 8 — Apply

```bash
atlantide apply infra.py --state demo.db -y
```

```
state: demo.db
demo ───────────────────────────────────────────────────────────────────────────
  + create  local.File:greeting
  + create  local.File:receipt

Plan: 2 to add

demo ───────────────────────────────────────────────────────────────────────────
  + done local.File:greeting
  + done local.File:receipt

Applied: 2 to add  (0.0s)

Outputs:
  default:greeting_checksum = 1caa462dd96fe06c4e4afa9476f5a2c59c39270f21a09e5a65602daee9def0e0
```

```bash
cat out/greeting.txt   # hello atlantide
cat out/receipt.txt    # 1caa462dd96fe06c4e4afa9476f5a2c59c39270f21a09e5a65602daee9def0e0
```

`receipt`'s content is `greeting`'s sha256. The `Ref` resolved at apply time,
after `greeting` was created.

**Code trace**

```
Engine.apply()                       engine/engine.py
  └─ _apply_compiled()               engine/engine.py
       ├─ apply_scope(plan, prior)   engine/locking.py # a pre-lock plan sizes the lease scope
       └─ _locked(run_replanned, scope, prepare=_alias_migration(ir))
            └─ with_lock()           engine/locking.py
                 ├─ backend.acquire_lock(owner, ttl, scope)
                 ├─ backend.bind_lease(lease)          # fences every subsequent write
                 ├─ background lease renewal
                 └─ run_replanned()  engine/engine.py
                      ├─ re-diff against freshly-loaded state
                      ├─ raise_drift(approved, fresh)   engine/drift.py
                      └─ executor.apply() -> _Applier.run() -> _run_phases()
                                            reconcile/executor.py
```

**The lock scope is the reachable graph, not the whole state.** Two runs touching
disjoint subgraphs do not block each other.

**The lease is renewed for as long as the run lives, and writes are fenced.** A
[`LeaseGuard`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/state/backend.py)
makes the store refuse a write from a lease that no longer holds the lock, so a
stalled run that resumes cannot corrupt state.

**Apply re-diffs under the lock**, because another run may have created a node in
the meantime. What executes could then differ from what was approved, so the
approved changeset is passed in as `expect` and any difference raises
`PlanDriftError`. `--allow-plan-drift` disables the check.

**Execution is a DAG scheduler**,
[`run_graph`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/graph/schedule.py).
Each node awaits its predecessors' `asyncio.Event` and only then takes the
concurrency semaphore. Awaiting dependencies before acquiring the semaphore
prevents a low `--parallelism` from deadlocking a deep graph. Each node is
wrapped in `asyncio.timeout(node_timeout)`.

**Execution runs in phases**: first create, update and replace over the desired
graph in topological order; then `_cbd_cleanup`, destroying the prior halves of
create-before-destroy replacements; then deletes over the *prior* graph in reverse
order.

On failure — including a `CancelledError` from Ctrl-C — the default
`--on-failure rollback` runs the recorded compensations in reverse. Rollback
failures surface as an `ExceptionGroup`. State is persisted one node at a time,
so a crash part-way through the graph leaves an accurate record.

---

## 9. Re-apply — the Merkle skip

```bash
atlantide apply infra.py --state demo.db -y
```

```
demo ───────────────────────────────────────────────────────────────────────────
  = noop    local.File:greeting
  = noop    local.File:receipt

Plan: 2 unchanged

nothing to apply
```

No provider calls were made; the engine compared hashes and stopped. With the AWS
provider, this avoids hundreds of API calls per re-run.

---

## 10. UPDATE vs REPLACE — per-field mutability

### Change a `mutable()` field

Edit `content` to `"hello world"`:

```bash
atlantide plan infra.py --state demo.db
```

```
demo ───────────────────────────────────────────────────────────────────────────
  ~ update  local.File:greeting
      content: 'hello atlantide' → 'hello world'
  ~ update  local.File:receipt
      content: {'$ref': 'demo:local.File:greeting #checksum'} → {'$ref':
'demo:local.File:greeting                         #checksum'}

Plan: 2 to change
```

`receipt`'s own input did not change — the `$ref` is identical on both sides —
yet it is an update.

This is Merkle propagation. `receipt`'s `input_hash` includes `greeting`'s hash,
so a change to `greeting` forces `receipt` to be reconciled, because the value
its reference resolves to is about to change.
[The Merkle hash](merkle.md#watch-the-ripple-with-real-numbers) shows the two
hashes that differ and the single `deps` entry that caused it.

```bash
atlantide apply infra.py --state demo.db -y
```
```
Applied: 2 to change  (0.0s)

Outputs:
  default:greeting_checksum = b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9
```
`out/receipt.txt` now holds the new checksum.

### Change an `immutable()` field

Edit `path` to `"out/hello.txt"`:

```
demo ───────────────────────────────────────────────────────────────────────────
  ± replace local.File:greeting
      path: 'out/greeting.txt' → 'out/hello.txt'
  ~ update  local.File:receipt
      ...

Plan: 2 to change
```

The result is `± replace` rather than `~ update`, determined by the
`immutable()` marker on the field. The downstream node is updated in both cases.

---

## 11. Drift, and the limit of the model

Modify the file outside the engine:

```bash
echo "TAMPERED" > out/greeting.txt
atlantide refresh --state demo.db -v
```

```
demo ───────────────────────────────────────────────────────────────────────────
  ~ drifted  local.File:greeting (1 of 2 inputs checked)
      checksum: 'b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2… →
'314cbe4410c173d9716307a8d25f58f61f3afe467a47f0272020ff3db2…
      not checked: content
  = in sync  local.File:receipt (1 of 2 inputs checked)
      not checked: content

Refresh: 1 drifted (state unchanged)
```

**`1 of 2 inputs checked`, and `not checked: content`.** Drift is only visible in
fields that the provider's `read` reports.
[`LocalProvider.read`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/providers/local/provider.py)
returns `checksum` and `path`, not `content`. Atlantide reports unchecked fields
instead of marking them in sync. `-v` names the unchecked fields; without it,
the output includes a one-line notice.

**`state unchanged`.** `refresh` is read-only by default. Add `--write` to record
what it found back into state.

The next step shows where the model differs from Terraform's:

```bash
atlantide refresh --state demo.db --write   # -> "1 drifted (state updated)"
atlantide plan infra.py --state demo.db
```
```
  = noop    local.File:greeting
  = noop    local.File:receipt

Plan: 2 unchanged
```

The modified file is not repaired. The diff compares desired inputs against
recorded inputs, and neither changed: `content` drifted but the provider cannot
report it, and `checksum` drifted but is `computed()`, so it never contributes to
a diff. The input set and the hash are unchanged, so the node is a no-op.

To force the repair:

```bash
atlantide apply infra.py --state demo.db -y --replace 'local.File:greeting'
```
```
  ± replace local.File:greeting
      (forced): None → None
  = noop    local.File:receipt

Applied: 1 to change, 1 unchanged  (0.0s)
```
`out/greeting.txt` is `hello world` again.

Hash-based diffing gives re-runs without provider calls and exact propagation.
The trade-off is that out-of-band changes to fields a provider cannot read are
invisible to `plan`. `refresh` detects drift, and `--replace` forces the repair.

---

## 12. Artifacts — build once, deploy anywhere

```bash
atlantide build infra.py -o demo.atlas
```
```
built demo.atlas — 2 nodes, hash f9ecb89e5ade…, pins {'local': '1.0.0'}
```

The `.atlas` file is the full canonical IR (shown in step 4) plus `ir_hash`,
`provider_pins`, `component_pins`, `policies` and `outputs`
([`ir/artifact.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/ir/artifact.py)).

```bash
atlantide verify demo.atlas
```
```
ok demo.atlas: hash and provider pins verified
```

`deploy` applies an artifact **without re-executing the config**:
`verify_artifact` → `rehydrate_resources`
([`engine/hydrate.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/engine/hydrate.py)) rebuilds
live `Resource` objects from the IR → the same `_apply_compiled` path as `apply`.

This supports promotion: build in CI, verify the hash, then deploy the identical
bytes to staging and to production. The config cannot evaluate differently in the
second environment, because it is not evaluated again.

---

## 13. Inspecting state

```bash
atlantide state list --state demo.db
```
```
                   2 resource(s)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━┓
┃ node                     ┃ type       ┃ status  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━┩
│ demo:local.File:greeting │ local.File │ created │
│ demo:local.File:receipt  │ local.File │ created │
└──────────────────────────┴────────────┴─────────┘
```

```bash
atlantide output --state demo.db
```
```
default:greeting_checksum = b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9
```

Also available: `state show`, `state backup` / `restore`, `state rm` (forget a
row without touching the provider), `state unlock` (break a dead run's lease),
`state check`, `state migrate`.

---

## 14. Destroy

```bash
atlantide destroy --state demo.db -y
```

```
demo ───────────────────────────────────────────────────────────────────────────
  - destroy local.File:greeting
  - destroy local.File:receipt

Plan: 2 to destroy

demo ───────────────────────────────────────────────────────────────────────────
  - done local.File:receipt
  - done local.File:greeting

Destroyed: 2 resource(s)  (0.0s)
```

The plan lists the nodes in graph order, but execution runs `receipt` before
`greeting`, because deletes run in reverse topological order.

`destroy` is implemented as a diff against an *empty* desired graph
([`engine/engine.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/engine/engine.py)), and
its `--target` closure runs over **dependents** rather than dependencies: destroy
a VPC and it pulls in everything sitting on top of it, not everything underneath.

`out/` is empty and `state list` reports `state is empty`.

---

## 15. Where to go next

- **Secrets** — `atlantide.secret("name")` is a *handle*; plaintext resolves in
  memory at apply and never enters the IR. Sensitive outputs are sealed at rest.
  See [`secrets/`](https://github.com/atlantide-org/atlantide/tree/main/atlantide/secrets/).
- **Policies** — `enforce("require-tags", keys=["env"])` at config top level;
  mandatory violations block `apply`. See [Policies](../reference/policies.md).
- **Components (L2)** — publishable from a git repo, pinned to commit + content
  hash, vendored locally. Worked example in
  [`examples/components/`](https://github.com/atlantide-org/atlantide/tree/main/examples/components/).
- **A real AWS graph** — [`examples/aws/example-one.py`](https://github.com/atlantide-org/atlantide/blob/main/examples/aws/example-one.py):
  per-env stacks, cross-stack outputs, IAM, Lambda with `code_path`
  fingerprinting, `SecretRef`, two enforced policies.
- **Writing a provider** — a provider is an ordinary Python package exposing a
  `ProviderPlugin` on the `atlantide.providers` entry-point group. The `local`
  provider is 80 lines and is the shortest complete example:
  [`providers/local/`](https://github.com/atlantide-org/atlantide/tree/main/atlantide/providers/local/).
- **When it goes wrong** — [When apply fails](failure.md) covers rollback and
  its limits; [Troubleshooting](../reference/troubleshooting.md) indexes every
  error by the stage that raises it.
- **Full reference** — the [CLI](../reference/cli.md), [Authoring](../reference/authoring.md),
  [Configuration](../reference/configuration.md) and
  [Remote state](../reference/remote-state.md) pages.

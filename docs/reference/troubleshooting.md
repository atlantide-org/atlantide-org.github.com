---
description: "Every Atlantide error by pipeline stage: what raised it, what it means, and how to fix it."
---

# Troubleshooting

Each error name identifies the failed stage. `--debug` before any command
(`atlantide --debug plan`) prints the full traceback and cause chain.

Stage numbers refer to [the pipeline](../how-it-works/index.md#the-whole-pipeline-on-one-page).

## Config does not compile (stages 1–2)

**`LanguageError`**: a construct outside the Atlas-lang subset. The message
names the construct, the line, and the replacement:

```
error: construct 'While' is not allowed in Atlas-lang — Atlas-lang has no
`while` (halting must be provable); use a bounded `for`. (line 2, col 0)
```

See [what config may not do](authoring.md#what-config-may-not-do). `import os`
fails the same way; imports are restricted to `atlantide.*`.

**`FuelExhaustedError`**: evaluation exceeded its step budget, usually from
runaway recursion (not rejected at parse time) or an oversized loop.

**`IRError`**: a value in a resource field cannot be canonicalized. Config data
must be plain JSON-shaped values.

**`RegistryError`**: an unknown or duplicate name, or a bad version: two
resources with one logical name in a stack, an uninstalled provider, or a
component alias that was never added.

## The graph is not a DAG (stage 4)

**`CycleError`**: resources depend on each other in a loop, named in the
message, typically two resources reading a field from each other. Pass a literal
on one side or split a resource.

**`StackOutputCycleError`**: cross-stack `output()` references form a loop, for
example `common:vpc_id -> dev:x -> common:vpc_id`. It is raised before lowering,
so the chain names output keys, not resources.

## The plan is refused (stage 7)

**`PreventDestroyError`**: a planned destroy targets a resource with
`Lifecycle(prevent_destroy=True)`, which `--replace` and `destroy` also honour.
To destroy it, remove the guard and re-plan.

**`PolicyViolationError`**: one or more mandatory policies failed and the apply
is blocked. `plan` exits `1`. Fix the resource, or set the binding to
`level=PolicyLevel.ADVISORY` to warn instead of block. See
[Policies](policies.md).

**`PolicyConfigError`**: a policy binding passes arguments the policy does not
accept, e.g. `enforce("require-tags", keys=3)`. The message names both.

## Locking and concurrency (stage 8)

**`LockError`**: another run holds the lease. Nothing was written. Wait, or
inspect holders with `atlantide state unlock`.

**`LeaseLostError`**: the run wrote to the provider, then found its lease taken
by another run. **Nothing is rolled back**, because a compensation is a state
write and the run no longer holds the lock. Run `atlantide refresh` before
applying again.

**`FencedWriteError`**: the store refused a write because another run is the
recorded holder. Unlike `LeaseLostError`, the store decides, not the run's local
clock, which can wrongly consider the lease valid. This conditional write
prevents two concurrent runs from silently merging state.

**`PlanDriftError`**: the changeset about to run differs from the approved one.
Apply re-diffs after acquiring the lease so that a resource created by another
run in the meantime is not built twice. The message names what was added and
what disappeared:

```
state changed between the plan you approved and the lock being taken, so the
changes are no longer the ones shown — now also: delete aws.S3Bucket:old.
Re-run to plan against current state.
```

Re-run. The difference is not reconciled automatically because it can contain
an unreviewed destroy.

## During apply

**`ProviderError`**: a provider CRUD call failed. It carries `node_id`, `op`
and `resource_type`. Under the default `--on-failure rollback`, completed nodes
are undone; see
[When apply fails](../how-it-works/failure.md).

**`RollbackError`**: a compensation (a provider call followed by a state write)
did not complete after a failed apply. State can describe a resource that no
longer exists, and because the stored hash still matches config, **the next plan
reports `NOOP`**. Run `atlantide refresh` before the next plan. Raised alongside
the original failure, never instead of it.

**`InterruptedRunError`**: Ctrl-C. Exits `130` instead of `1`, without the
`error:` prefix. Completed nodes are compensated on exit where the run still
held its lock.

## State, secrets, artifacts, components

**`StateError`**: a state backend operation failed. For a remote backend,
`atlantide state check` verifies reachability and setup in one pass.

**`SecretsError`**: sealing or unsealing failed: unknown backend, wrong key, or
corrupt ciphertext. If `plan` warns that *every* secret appears rotated and none
intact, the keyfile is wrong. See [Secrets](remote-state.md#secrets).

**`ArtifactError`**: a `.atlas` artifact is malformed, corrupted, or fails its
hash check. `atlantide verify` runs that check on its own.

**`ComponentError`**: fetching, vendoring or verifying a component failed: a bad
git source, a missing `--subdir`, or a vendored tree whose hash does not match
`atlantide.lock`. `atlantide component vendor` rebuilds
`.atlantis/` from the lock; `component verify` re-hashes it.

## Things that are not errors

**A plugin that failed to load.** `atlantide providers` lists it and exits `1`.
Config cannot find its types, which resembles a typo. `--no-plugins` ignores all
installed plugins.

**A plan that shows changes you did not make.** The diff compares desired inputs
against *recorded* inputs, not the live world: the config or the state
changed. To compare against the cloud, run `atlantide refresh`.

**A resource the provider could not find during `refresh`.** It is reported but
kept unless `--prune` is given, because discarding the record would make the
next apply create a second one.

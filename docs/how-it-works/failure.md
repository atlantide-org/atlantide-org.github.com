---
description: "What happens when apply fails: phases, compensation in reverse order, what cannot be rolled back, and poisoned rows."
---

# When apply fails

A plan can fail part-way through. This page describes what the engine does next.

```bash
atlantide apply --on-failure rollback   # default: undo what this run completed
atlantide apply --on-failure halt       # stop where it stands, undo nothing
```

## The three phases

Apply runs in phases. Only the first is reversible.

| Phase | What runs | Order | Reversible |
|---|---|---|---|
| 1 | `CREATE`, `UPDATE`, `REPLACE` | dependencies first, in parallel | **yes** |
| 1b | the destroy half of a create-before-destroy `REPLACE` | dependents first | no — terminal |
| 2 | `DELETE` | dependents first | no — terminal |

Phases 1b and 2 are terminal: recreating a destroyed resource would lose its
identity and outputs, so a failure there is reported, not compensated. Committed
stack outputs are persisted only after all three phases succeed.

## The compensation saga

Under the default `--on-failure rollback`, every node that completes in phase 1
records an undo. On failure the undos run in **reverse completion order**, not
reverse graph order, so they follow what this run actually did.

| What was applied | What the undo does |
|---|---|
| `CREATE` | `provider.delete`, then drop the state row. The resource carries the outputs of its create — notably its id — so the delete acts on that resource directly rather than locating it by attributes, which could match an unrelated resource sharing them. |
| `UPDATE` | `provider.update` back to the prior values, then restore the prior state row verbatim, still sealed. |
| `REPLACE` | Undo the create half, then restore the prior resource and its recorded outputs. |

The saga catches `BaseException`, not `Exception`. An interrupt arrives as a
cancellation; catching only `Exception` would skip compensation on a Ctrl-C
during an apply that has already created resources.

## When rollback does not run

**A run that lost its lease is not rolled back.** A compensation is a provider
call and a state write, and a run that no longer holds the lock may be racing the
run that took it; undoing "its" creates could destroy the other run's resources.
The resources are left in place, and the report states this.

This is the only case in which `--on-failure rollback` does not roll back. Recover with `atlantide refresh`.

## When rollback itself fails

An undo is a provider call followed by a state write. A failure between the two
leaves state describing a resource that no longer exists. Because the diff is
symbolic, that row's stored hash still matches config, so the next plan would
report `NOOP` and the divergence would stay hidden permanently.

To prevent this, the engine **poisons** the row before running a node's
compensation: it clears the row's `input_hash` so the next plan cannot
Merkle-skip it. The undo's own state write clears the poison when it succeeds.
Poisoning afterwards would only take effect on an exception; a process killed
mid-rollback would leave the row untouched and the divergence silent.

When compensations fail, the original error and the rollback errors are raised
together as a group, and every leaf is rendered. The rollback failure never
replaces the apply failure.

## Interrupts

The first Ctrl-C cancels the run and follows the failure path above: under the
default, completed nodes are compensated on the way out. The exit code is `130`.

A second Ctrl-C abandons that cleanup. Each compensation is *shielded*, so the
press cannot cancel an undo between its provider call and its state write — the
window poisoning makes visible — but the CLI's hard exit still takes effect.
State may then not describe what exists: run `atlantide refresh` before applying
again.

The second press does **not** release the run's lock. An abandoned run may still
have provider calls in flight, so the lease is left to lapse, or to be cleared
with `atlantide state unlock`, rather than handed to a second writer.

## The re-diff before anything runs

Apply does not execute the changeset that `plan` printed. Once it holds the
lease, it re-diffs against freshly loaded state; otherwise a resource that
another run created in the meantime would still be planned as a `CREATE` and
built twice.

The approved plan and the plan about to execute can therefore differ, and that
difference could include an unreviewed destroy. When they differ, the run stops
with a `PlanDriftError` naming what appeared and what disappeared.

## After a failed run

```bash
atlantide refresh          # what actually exists, vs what state records
atlantide state list       # what state records
atlantide state unlock     # who holds the lease
```

`refresh` is the recovery command in every case above. It is read-only unless
given `--write`. A resource the provider cannot find is reported but kept unless
`--prune` is also given.

See [Troubleshooting](../reference/troubleshooting.md) for the errors these paths
raise.

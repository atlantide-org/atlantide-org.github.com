---
description: "Every command: init, import, refresh, targeting with -t and --env, interrupts, diagnostics, exit codes, secrets, components and state."
---

# CLI

```bash
atlantide init                                # scaffold a project
atlantide plan    infra.py                    # preview changes
atlantide apply   infra.py                    # reconcile (parallel)
atlantide refresh                             # detect drift vs live state
atlantide graph   infra.py --format mermaid   # dependency graph
atlantide destroy                             # tear down
```

## Starting a project

`atlantide init [DIRECTORY]` writes `atlantide.toml`, a starter config and a
`.gitignore`, then compiles the config before reporting success. `--template`
takes `minimal` (default; `local` provider, no credentials) or `aws`.
`--state local|s3|postgres` writes the matching `[state]` table. See
[Installation](../install.md#scaffolding-a-project) for all flags.

## Adopting existing resources

`atlantide import` records an existing resource in state, so the next `plan`
reports it unchanged instead of proposing to create it. It creates, updates and
deletes nothing.

```bash
atlantide import                                  # list what is importable, and how
atlantide import aws.S3Bucket:assets              # located by name
atlantide import aws.Vpc:main vpc-0abc123         # located by a provider id
atlantide import aws.Vpc:main vpc-0abc123 --dry-run
```

Declare the resource in config first, then pass its node id. Some types are
located by name; others need a provider-assigned id that config cannot know,
such as a VPC's `vpc_id` or a certificate's `arn`. `import` with no arguments
lists which types need which.

**A resource whose live values differ from config is not imported.** Reconcile
the config, or pass `--allow-drift` to import it anyway; the next plan then
shows the update. `-v` names the fields the provider's read did not cover.

To undo an import, run `atlantide state rm <node>`. It removes the state row and
leaves the resource in place.

## Detecting drift

`atlantide refresh` reads live provider state and reports how it differs from
recorded state. It is read-only unless `--write` is given, which syncs drifted
outputs back to state.

A resource the provider cannot find is reported but **kept** in state unless
`--prune` is also given. Removing it on a single failed read would cause the
next apply to create a second copy.

Drift is detected only in fields the provider's `read` reports. The report
states how many of each resource's inputs were covered; `-v` names the rest.

## Common options

State defaults to `atlantide.db`. Override it with `--state`.

The mutating commands (`apply`, `deploy`, `destroy`, `refresh`) accept
`--confirm/-y`, `--region` and `--parallelism/-p`. Commands that write state
also accept `--on-failure rollback|halt`. The default, `rollback`, undoes the
nodes a failed run already completed.

## Narrowing a run

`--target/-t` accepts a full node id, a short form, or a glob:

```bash
atlantide apply   -t aws.S3Bucket:assets        # and its dependencies
atlantide destroy -t aws.Vpc:main               # and its dependents
atlantide apply   --replace aws.LambdaFunction:worker
```

`apply` includes the target's dependencies; `destroy` includes its dependents.

A pattern that matches nothing is an error, not an empty run. `--replace` still
honours `prevent_destroy`.

`--env/-e` narrows a run to one environment of the config's
[`Config`](configuration.md#environments). It is repeatable:

```bash
atlantide plan  --env prod                      # prod only
atlantide apply --env dev --env staging
```

An unselected environment is **out of scope, not undeclared**: its recorded
state is not diffed and is never planned for deletion. The plan lists the
environments it excluded:

```
envs: prod (of dev, prod) — dev is not planned and will not change
```

Naming an environment the config does not declare is an error. Stacks declared
outside the `config.envs()` loop, such as a shared `common`, are not part of the
matrix and stay in the graph.

`plan`, `apply`, `validate` and `build` accept `--env`. `build` records the
selection in the artifact, so a later `deploy` covers the same environments.
`destroy` also accepts it but selects by stack, because it reads state only, not
config, and an environment's stack is its name.

`--target` and `--env` can be combined. A target that matches only excluded
environments is an error.

## Interrupting a run

Ctrl-C cancels the run and follows the failure path. Under the default
`--on-failure rollback`, resources already created are undone, then the process
exits with code 130.

A second Ctrl-C abandons the cleanup. State may then not match what exists; run
`atlantide refresh` before applying again.

The second press does **not** release the run's lock, because the abandoned run
may still have provider calls in flight. The lease expires on its own, or can be
cleared with `atlantide state unlock`.

## Output and diagnostics

`--log-level debug|info` traces a run to stderr; `--log-format json` makes the
stream machine-readable. `--audit-log FILE` appends every run's events to a
JSONL file. These are global options and go before the command:

```bash
atlantide --log-level debug --log-format json plan
atlantide --debug apply           # full traceback on error
```

`--json` is a per-command option that replaces the rendered output on stdout.
See [CI and automation](ci.md#machine-readable-output).

Every command that touches state first prints which state it uses:

```
state: s3://acme-atlantide-state/prod/atlantide.json
```

Under `--json` the same value appears as the payload's `state` field.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. With `--detailed-exitcode`: nothing to do — no pending changes, no drift. |
| `1` | An error, **or** a mandatory policy denied the plan, **or** (`providers`) a plugin failed to load. |
| `2` | Only with `--detailed-exitcode`: `plan` has changes pending, or `refresh` found drift. |
| `130` | The run was interrupted (Ctrl-C). |

Without `--detailed-exitcode`, `plan` exits `0` whether or not changes are
pending. Use it to gate CI:

```bash
atlantide plan --detailed-exitcode || case $? in
  2) echo "changes pending" ;;
  *) exit 1 ;;
esac
```

A denied plan exits `1` with or without `--detailed-exitcode`.

## Other commands

**`build` / `verify` / `deploy`**: produce, check and apply portable `.atlas`
artifacts. An artifact is content-hashed with provider versions pinned, so a
config compiled once can be promoted between environments as identical bytes.

**`validate`**: check that a config compiles, stays within the Atlas-lang
subset and has an acyclic graph. It touches no state and calls no provider, so
it needs no credentials. Use it in pre-commit hooks and pull-request checks,
where `plan` would need access to a state backend.

**`output`**: print the values a previous apply exported. It reads only state,
so it works while the config is being edited:

```bash
vpc=$(atlantide output vpc_id)
```

Sensitive values require `--reveal`.

**`state`**: inspect and administer the state store. See
[Remote state](remote-state.md).

**`secret`**: manage the local AES-GCM encrypted name-to-value store:

```bash
atlantide secret set app/signing-key       # value prompted (hidden) if omitted
atlantide secret get app/signing-key -r    # print plaintext (--reveal required)
atlantide secret list                      # names only, no values
atlantide secret rm  app/signing-key
```

**`component`**: `add`, `lock`, `vendor` and `verify` for published components.

**`providers`**: list the provider plugins this installation can see, including
any that failed to load. Without this, a failed plugin shows up only as config
being unable to find its types.

**`resources` / `schema`**: list the available resource types, and show one
type's fields and their mutability.

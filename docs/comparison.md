---
description: "Terraform, Pulumi and CDK vocabulary mapped to Atlantide, key differences, current limitations, and migration."
---

# Coming from Terraform, Pulumi or CDK

Like these tools, Atlantide declares infrastructure, diffs it against recorded
state, and reconciles the difference. It differs in how determinism is enforced
and in how much of the engine is exposed.

## Vocabulary

| You know | Here it is called | Notes |
|---|---|---|
| `terraform plan` / `apply` | `atlantide plan` / `apply` | `plan` needs no credentials. |
| HCL / TypeScript program | Atlas-lang config (`infra.py`) | Real Python, executed by a bounded interpreter. |
| Provider | Provider | Python packages, discovered by entry point. |
| Module / `ComponentResource` / Construct | [Component](reference/components.md) | Python; config uses them but cannot define them. |
| `terraform init` | [`atlantide component add`](reference/components.md) | Pins to a commit + content hash. |
| Backend / remote state | [State backend](reference/remote-state.md) | SQLite, S3+DynamoDB, or Postgres. |
| `terraform import` | [`atlantide import`](reference/cli.md#adopting-existing-resources) | Refuses to import a resource that differs from config. |
| `terraform refresh` | [`atlantide refresh`](reference/cli.md#detecting-drift) | Read-only unless `--write`. |
| `depends_on` | `depends_on` | Rarely needed; reading a field creates the edge. |
| `lifecycle { prevent_destroy }` | `Lifecycle(prevent_destroy=True)` | Plus `create_before_destroy`, `ignore_changes`, `aliases`. |
| `moved` block | `Lifecycle(aliases=(...))` | Rename without replace. |
| `terraform output` | `atlantide output` | Sensitive values need `--reveal`. |
| Workspace | [Stack](reference/authoring.md#stacks) + [`Config` environment](reference/configuration.md#environments) | Both in-config: one `Config` declares the environment matrix, `--env` selects. |
| `terraform workspace select` | [`--env`](reference/cli.md#narrowing-a-run) | An unselected environment is out of scope, never planned for deletion. |
| `*.tfvars` | [Inputs](reference/configuration.md#inputs) + [profiles](reference/configuration.md#profiles) | Inputs are per-run values; profiles point a run at a state backend/account. |
| Sentinel / OPA | [Policies](reference/policies.md) | Native Python, evaluated at plan time. |
| Terraform Registry | No central registry | Components are git URLs, pinned by commit. |

## Key differences

**A real language, but a bounded one.** Pulumi and CDK use a full programming
language, so a config's plan can depend on the clock, the environment or a network
call. Terraform avoids this by not being a programming language. Atlantide configs
are Python (typed and `mypy`-checkable) but run under
[Atlas-lang](reference/authoring.md#what-config-may-not-do), an interpreter with
no clock, randomness, environment, network or filesystem. The interpreter enforces
determinism.

**The diff is a Merkle comparison, not a per-resource read.** Each node's hash
folds in its dependencies' hashes, so an unchanged subgraph is skipped without any
provider call. See [The Merkle hash](how-it-works/merkle.md).

**`plan` needs no credentials.** Everything up to the diff is pure computation
over the config and the recorded state. `validate` can run in a pre-commit hook,
and `plan` can run on a pull request with read access to state and no provider credentials.

**Per-field mutability is in the type.** Every field is declared `mutable()`,
`immutable()` or `computed()`, so whether a change is an in-place update or a
replacement is known from the type, before any plan runs.

**Build once, deploy anywhere.** `atlantide build` compiles a config into a
content-hashed `.atlas` artifact with provider versions pinned. `deploy` applies
the artifact without re-executing the config, so staging and production receive
identical bytes.

## Limitations

- **Limited provider coverage.** Three built-in providers and about two dozen AWS
  resource types, compared with thousands in Terraform. `atlantide resources`
  lists what exists. The plugin interface is open; there is no third-party
  provider ecosystem.
- **No central registry.** Components are git URLs you pin yourself.
- **No HCL interoperability.** Atlantide cannot read Terraform configuration or
  state. Existing resources are adopted one at a time with `atlantide import`.
- **Versioned state format.** The format can change between minor releases. It
  migrates forward automatically, and an older atlantide refuses a newer store.
- **Beta.** The package is classified as beta.

## Migration

There is no converter. Migration proceeds in slices:

1. Write the config for a slice of existing infrastructure.
2. `atlantide validate`, then `atlantide plan` — everything will show as
   `CREATE`, because state knows nothing yet.
3. `atlantide import` each resource. A resource whose live values differ from
   config is refused, not adopted, so this step also checks that the config
   matches what is deployed. `--dry-run` previews the import without changing
   state.
4. `atlantide plan` again. The slice should now be entirely `NOOP`.

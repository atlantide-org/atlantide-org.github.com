---
name: atlantide
description: Write, validate and plan Atlantide infrastructure configs (infra.py, atlantide.toml). Use when a project contains atlantide.toml or imports atlantide, or when asked to add, change or debug infrastructure declared with Atlantide.
---

# Atlantide

Atlantide is typed, deterministic Infrastructure-as-Code for Python. A config
(`infra.py` by default) is ordinary Python syntax executed by **Atlas-lang**, a
bounded interpreter with no clock, randomness, environment, network or
filesystem. Same config + same inputs = byte-identical plan.

Full docs as Markdown: https://atlantide-org.github.io/llms.txt
(`llms-full.txt` is everything in one file.)

## Safety

- `validate`, `plan`, `graph`, `resources`, `schema`, `providers`, `output` and
  `state list`/`state show` are read-only. Run them freely.
- `apply`, `deploy`, `destroy`, `import`, `refresh --write`, `state rm`,
  `state restore`, `state migrate` and `state unlock` change real infrastructure
  or its record. **Do not run them unless the user asked for that specific
  action.** Never pass `-y`/`--confirm` on their behalf.
- Never put a secret value in config, in `-var`, or in `atlantide.toml`. Use
  `atlantide.secret("name")`; the user sets the value with
  `atlantide secret set name`.
- Do not commit `atlantide.key`, `atlantide.secrets`, `atlantide.db*` or
  `.atlantis/`. Do commit `atlantide.lock`.

## The loop

1. Find the project root: the nearest `atlantide.toml` going upwards. It names
   the config file and state backend, so commands need no flags inside it.
2. Discover what exists — from the installed CLI, not from memory:
   ```bash
   atlantide resources              # every resource type this install can see
   atlantide schema aws.S3Bucket    # fields, types, mutability, defaults
   ```
3. Edit the config.
4. `atlantide validate --json` — subset check, graph, cycles. No credentials.
5. `atlantide plan --json --detailed-exitcode` — exit `0` no changes, `2`
   changes pending, `1` error or policy denial.
6. Report the plan to the user. Pay attention to every `REPLACE` and `DELETE`:
   `REPLACE` means an `immutable()` field changed and the resource will be
   destroyed and recreated.

For the full traceback, put `--debug` before the command:
`atlantide --debug plan`. The same goes for the other global options,
`--profile/-P`, `--log-level`, `--audit-log` and `--no-plugins`.

## Atlas-lang: what config may not do

The subset is enforced before evaluation. Rejected:

| Construct | Use instead |
|---|---|
| `while` | bounded `for` |
| `class` | only a module-level `EnvSchema` subclass with annotated fields; components and resource types live in Python packages |
| `try` / `raise` / `assert` | guard with `if` |
| `match` | `if` / `elif` |
| `async` / `await`, `yield` | plain functions, comprehensions |
| `global` / `nonlocal`, `:=`, `del` | plain assignment |
| `import os`, `time`, `random`, … | only `atlantide.*` imports are allowed |
| `open`, `eval`, `exec`, `getattr`, `setattr`, `hasattr`, `globals`, `vars` | not available |

Allowed: functions, lambdas, `if`, `for`, comprehensions, f-strings, `with`.
Evaluation runs on a fuel budget; runaway recursion ends in
`FuelExhaustedError`.

Pure helpers are globals (no import): `slugify`, `uuid5`, `sha256_hex`,
`hmac_sha256_hex`, `b64encode`, `b64decode`, `to_json`, `from_json`, `merge`.
The `atlantide` global gives `atlantide.input(name, default)` and
`atlantide.secret(name)`.

## Shape of a config

```python
from atlantide.core import Config, EnvSchema, Lifecycle, Stack, concat, output
from atlantide.policy import enforce
from atlantide.providers.aws import S3Bucket, SqsQueue

enforce("require-tags", keys=["env"])                     # top level, outside any Stack
enforce("deny-destroy-in-protected", stacks=["prod"])

class AppEnv(EnvSchema):                                  # annotated fields only
    versioning: bool = False

config = Config(AppEnv, envs={
    "dev":  {"region": "eu-north-1", "tags": {"env": "dev"}},
    "prod": {"region": "eu-north-1", "tags": {"env": "prod"}, "versioning": True},
})

for env in config.envs():
    with Stack(env.name, config=env, name_prefix="acme"):
        assets = S3Bucket(
            "assets",
            versioning=env.versioning,
            lifecycle=Lifecycle(prevent_destroy=True),
        )
        jobs = SqsQueue("jobs", fifo=True)
        output("assets_arn", assets.arn)
        output("assets_objects", concat(assets.arn, "/*"))
```

## Rules that matter

- **Dependencies come from reads.** `assets.arn` returns a lazy `Ref`, and
  reading it creates the graph edge. Use `depends_on=[x]` only when the
  dependency carries no value.
- **A `Ref` is not a string.** Build strings from one with `concat(...)`,
  `interpolate("https://{}", ref)` or `join(sep, parts)` from `atlantide.core`.
  `"x" + ref` fails at evaluation, but **an f-string such as `f"{ref}"`
  validates and plans cleanly and writes the literal text
  `Ref(node_id=..., attr=...)` into the resource.** Never put a `Ref` in an
  f-string.
- **Logical names are identifiers**, unique per type within a stack. Node
  ids are `{stack}:{type}:{name}`, e.g. `prod:aws.S3Bucket:assets`.
- **Renaming a resource destroys it** unless the new one carries
  `lifecycle=Lifecycle(aliases=("old_name",))`.
- **Per-environment differences go in `Config`**, as typed `EnvSchema` fields —
  not as branches on the stack name and not as inputs. `region`, `tags` and
  `name_prefix` are implicit keys every environment may set.
- **Per-run values** (a build number, a fork prefix) are
  `atlantide.input("name", default)` and arrive as strings.
- **`with region("us-east-1"):`** overrides the region for one block, e.g. an
  ACM certificate for CloudFront.
- **Another config's stack:** `StackReference("network").output("vpc_id")`.
- **Data sources** such as `AwsCallerIdentity` and `AwsAvailabilityZones` read
  account facts; use them instead of hardcoding zone letters or account ids.
- **`Subnet` requires `availability_zone`**; `LambdaFunction` requires
  `code_path=` or `s3_bucket=` + `s3_key=`; `S3Bucket` needs
  `force_destroy=True` to be deletable while non-empty.

## Commands

```bash
atlantide init [--template minimal|aws]     # scaffold; minimal needs no credentials
atlantide validate                          # compile only
atlantide plan [--env prod] [-t <node>]     # preview; --env and -t narrow the run
atlantide graph --format mermaid            # dependency graph
atlantide output [name]                     # values exported by the last apply
atlantide state list | state show <node>    # what state records
atlantide refresh                           # read-only drift report
```

`--json` is supported by `plan`, `apply`, `validate`, `refresh`, `import`,
`init`, `output`, `providers`, `state list` and `state show`.

## Errors

| Error | Meaning and fix |
|---|---|
| `LanguageError` | Construct outside Atlas-lang; the message names the line and the replacement. |
| `FuelExhaustedError` | Runaway recursion or an oversized loop. |
| `IRError` | A field value is not JSON-shaped data. |
| `RegistryError` | Duplicate logical name, unknown type, missing provider, or unknown component alias. |
| `CycleError` | Two resources read from each other; pass a literal on one side. |
| `PolicyViolationError` | A mandatory policy failed; fix the resource (usually missing tags). |
| `PreventDestroyError` | The plan destroys a `prevent_destroy` resource; surface to the user, do not remove the guard yourself. |
| `LockError` | Another run holds the state lease; wait. |
| `PlanDriftError` | State changed after the plan was shown; re-plan. |
| `RollbackError`, `LeaseLostError` | State may not match reality; tell the user to run `atlantide refresh`. |

A plan showing changes nobody made means config or *state* changed — the diff
is against recorded inputs, not the live cloud. `refresh` compares with reality.

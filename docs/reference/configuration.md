---
description: "Environments (Config and EnvSchema), per-run inputs, the atlantide.toml project file, and profiles."
---

# Configuration

Atlantide has three kinds of configuration:

| | What it is | Where it lives | Selected by |
|---|---|---|---|
| [Environments](#environments) | The typed matrix of environments the system has, and what differs between them | `Config(...)` in the config file | `--env` |
| [Inputs](#inputs) | A per-run value from outside the repository | `-var`, `--var-file`, `[inputs]` | supplied per run |
| [Profiles](#profiles) | Where a run points: state backend, AWS profile, parallelism | `[profile.<name>]` in `atlantide.toml` | `--profile/-P` |

`--profile` and `--env` are independent; neither implies the other.

## The project file

`atlantide.toml` sets the config path, the state database and other defaults,
so commands inside the project need no flags.

The file is found by searching the working directory and then each parent, as
git locates a repository root. Relative paths in it resolve against the
directory containing the file, not the directory the command runs from.

```toml
config       = "infra.py"
state        = "atlantide.db"
parallelism  = 8
aws_region   = "eu-north-1"
aws_profile  = "default"
aws_endpoint = "http://localhost:4566"   # send every AWS call here instead
secrets_key   = ".atlantide.key"
secrets_store = ".atlantide.secrets"

[aws.aliases.prod]                       # alternate account (multi-account)
profile  = "prod-account"                # a resource selects it via provider_alias="prod"
```

## Environments

A `Config` declares every environment and what differs between them, in one
place:

```python
from atlantide.core import Config, EnvSchema, Stack

class AppEnv(EnvSchema):
    domain: str
    size: int = 1

config = Config(
    AppEnv,
    envs={
        "dev":  {"region": "eu-north-1", "domain": "dev.example.io"},
        "prod": {"region": "us-east-1",  "domain": "example.io", "size": 5},
    },
)

for env in config.envs():                     # env: AppEnv
    with Stack(env.name, config=env):
        ...
```

Each variable declares a type and an optional default. All values are checked
when the `Config` is constructed, so a missing or mistyped prod value fails
`atlantide validate` in CI rather than the prod apply.

An environment name becomes the stack name, so it must be an identifier.

### The schema

`EnvSchema` is the only class Atlas-lang accepts: a module-level class whose body
contains annotated fields only, with no methods, decorators or metaclass.
Because the variables are ordinary attributes, an editor completes
`env.domain`, and `env.domian` is a type error before anything runs.

A field may be annotated `str`, `int`, `float`, `bool`, `list` or `dict`, or
`X | None` to make it optional and nullable. Parameterized generics such as
`list[str]` are not supported.

Alternatively, the schema can be a mapping of `var()` declarations, which
provides no static type information:

```python
from atlantide.core import Config, var

config = Config(schema={"size": var(int, default=1)}, envs={...})
```

Both forms run the same validation. A `var()` without a default is required:
every environment must supply it, and a missing value is reported when the
`Config` is built, not where the value is read. `default=None` makes it
optional.

### Well-known keys

`region`, `tags` and `name_prefix` are implicit in every schema, so
`Stack(env.name, config=env)` needs no separate `region=`:

```python
with Stack(env.name, config=env):          # region/tags/name_prefix from the env
    ...
```

An explicit `Stack` argument takes precedence over the environment, except
`tags`, which merge (the stack's own taking precedence). A schema may
re-declare a well-known key to make it required or to narrow its type.

Inside the body the environment is ambient: a [component](components.md) reads
it with `current_config()` instead of receiving it through a constructor.

### Selecting one

```bash
atlantide plan  infra.py --env prod            # prod only
atlantide apply infra.py --env dev --env prod  # repeatable
```

An unselected environment is **out of scope, not undeclared**: its state is
never diffed or planned for deletion, and the plan lists what it excluded.

```
envs: prod (of dev, prod) — dev is not planned and will not change
```

Naming an environment the config does not declare is an error. Stacks declared
*outside* the `config.envs()` loop, such as a shared `common`, are not part of
the matrix and are unaffected by `--env`, so a shared VPC stays in the graph
when a run is narrowed.

`--env` is accepted by `plan`, `apply`, `validate`, `build` and `destroy`. On
`destroy` it selects by stack name, because destroy reads state only, not
config, and an environment's stack is its name.

`build` records the selection in the `.atlas` artifact, so `deploy` covers
the same environments as the build. Determinism is over *(config, inputs,
selected environments)*.

## Inputs

An input is a per-run value supplied from outside the repository, such as a CI
build number or a fork's name prefix. Inputs arrive as text:

```python
env = atlantide.input("env", "dev")      # with a default
count = int(atlantide.input("count"))    # values arrive as strings from -var
```

```bash
atlantide plan -var env=prod
atlantide plan --var-file prod.toml
```

Inputs can be set in three places, in increasing order of precedence:
`[inputs]` in `atlantide.toml` (or `[profile.<name>.inputs]` for one profile),
`--var-file`, and `-var` on the command line.

Every plan prints the inputs it read. Only inputs the config reads affect the
result.

!!! note "An input is not an environment"
    Values that differ *between environments* belong in a
    [`Config`](#environments), which is checked in, typed and validated at
    construction. Values that differ *between runs of one environment* are
    inputs. An environment's value may be built from an input.

!!! warning "Inputs are not for secrets"
    `atlantide.secret("name")` returns a handle, not a value. A secret passed as
    an input is written in plaintext to the IR, build artifacts and state.

## Profiles

A `[profile.<name>]` table overlays the top level and is selected with
`--profile/-P` or the `ATLANTIDE_PROFILE` environment variable. A profile sets
where a run points: state backend, AWS account and parallelism.

The overlay is applied per table, so a profile sets only the keys it changes and
inherits the rest:

```toml
parallelism = 4

[profile.prod]
parallelism = 16

[profile.prod.state]                     # inherits the base [state] keys it omits
backend    = "s3"
bucket     = "acme-atlantide-state"
key        = "prod/atlantide.json"
lock_table = "atlantide-locks"
```

Naming a profile the file does not define is an error; there is no fallback to
the defaults.

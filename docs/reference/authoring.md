---
description: "Writing a config: resources, stacks, outputs, lifecycle, depends_on, output combinators, derived values, inputs, secrets, and what Atlas-lang rejects."
---

# Authoring

Reference for config constructs and their effects. For step-by-step
introductions, see the [walkthrough](../how-it-works/walkthrough.md) and
[Building on AWS](../aws/index.md).

## Declaring a resource

```python
Resource("logical-name", **fields, lifecycle=..., depends_on=[...])
```

The logical name is positional and must be an identifier. Every resource
accepts `lifecycle=` and `depends_on=`; all other arguments are the type's own
fields, whose mutability determines the effect of changing them. Run
`atlantide schema <type>` to list them.

Reading another resource's computed field returns a lazy `Ref`, not a value.
The read creates the dependency edge, with no string addresses, and resolves at
apply.

## Stacks

```python
with Stack("prod", region="eu-north-1", tags={"env": "prod"}, name_prefix="acme"):
    ...
```

A stack scopes everything declared in its body. Resources inside get the node id
`{stack}:{type}:{name}`.

- **`region`** is required. It is the default for every resource in the body
  that has a `region` field and does not set one.
- **`tags`** are merged into every resource in the body that has a `tags` field.
  Nested stacks merge, with the inner stack taking precedence; a resource's own
  tags take precedence over the stack's.
- **`name_prefix`** composes the cloud name of resources whose name field is
  marked `physical_name` as `{name_prefix}-{base}-{stack}`. If omitted, the
  enclosing stack's value is used.
- **`config`** is one environment of a [`Config`](configuration.md#environments).
  Its `region`, `tags` and `name_prefix` keys fill in the matching arguments, and
  the environment is ambient in the body. An explicit argument takes precedence
  over the environment; `tags` merge.

Stacks nest, and a config may declare any number of them. The common pattern is
a loop over the environments of a `Config`:

```python
for env in config.envs():
    with Stack(env.name, config=env):
        S3Bucket("assets", versioning=env.versioning)
```

Per-environment differences are then typed, declared variables rather than
branches on the stack name. See [Environments](configuration.md#environments).

### Per-block region

`with region("us-east-1"):` overrides the enclosing stack's region for the
resources declared inside it, and nothing else. A typical use is a resource a
service requires in a specific region, such as an ACM certificate for
CloudFront.

## Outputs

```python
output("assets_arn", assets.arn)
```

`output()` exports a literal or a `Ref` under a name, namespaced by the
enclosing stack: inside `with Stack("prod")` it becomes `prod:assets_arn`;
outside any stack it goes in `default`. Outputs are persisted to state after
apply and read with `atlantide output`.

`output()` also returns a handle. A later stack in the same config can use it
to consume the value; the reference becomes a dependency edge rather than a
state lookup.

A stack applied by a **separate** config must be referenced explicitly:

```python
vpc_id = StackReference("network").output("vpc_id")
```

`StackReference` resolves from the referenced stack's committed outputs at
apply, so that stack must already be applied to the same state store.

## Lifecycle

```python
S3Bucket("assets", lifecycle=Lifecycle(prevent_destroy=True), ...)
```

| Field | Effect |
|---|---|
| `prevent_destroy` | A planned `DELETE` — or the destroy half of a `REPLACE` — on this resource fails the whole plan. |
| `create_before_destroy` | A `REPLACE` creates the replacement before destroying the old one. Falls back to destroy-first when the two would collide on identity. |
| `ignore_changes` | Field names whose drift is ignored: excluded from the Merkle `input_hash` and from the diff's changed-field set, so a change to one never triggers `UPDATE` or `REPLACE`. |
| `aliases` | Prior node ids (or bare old logical names) this resource was **renamed from**. |

### Rename without replace

To rename a resource without recreating it, list its previous name as an alias.
The engine maps it onto the existing state entry:

```python
S3Bucket("assets_v2", lifecycle=Lifecycle(aliases=("assets",)), ...)
```

When the new id is absent from state and an alias id is present, the plan
rewrites the existing row to the new id.

To guard a whole stack rather than one resource, see
[`deny-destroy-in-protected`](policies.md#deny-destroy-in-protected).

## Explicit ordering

`depends_on=[other]` orders one resource after another without reading a value
from it. Use it for dependencies that carry no value, such as an IAM policy that
must propagate before a dependent service starts, or a bucket policy that must
exist before an upload.

Reading a field such as `other.arn` already creates the edge; `depends_on` is
needed only when nothing is read. Pass the resources or their node ids.

The edge is excluded from the content hash, so adding one changes ordering only
and never causes a resource to be re-planned.

## Output combinators

`concat`, `interpolate` and `join` build strings from values that are not yet
known. A computed field such as `assets.arn` is a `Ref`, so ordinary string
formatting does not apply to it.

```python
S3BucketPolicy("p", bucket=assets.bucket, statements=[
    allow("s3:GetObject", on=concat(assets.arn, "/*"), principal="*"),
])
```

!!! warning "Never put a `Ref` in an f-string"
    `"arn:" + assets.arn` fails at evaluation, but `f"arn:{assets.arn}"` does
    not: it validates, plans cleanly, and writes the literal text
    `Ref(node_id=..., attr=...)` into the field. Use `interpolate("arn:{}",
    assets.arn)` instead.

Combinators serialize as data, not closures. The config is not re-executed at
apply; the engine evaluates the recorded operation once the referenced values
resolve.

## Derived values

Atlas-lang provides a set of deterministic pure functions in the global
namespace for values computed *at config-evaluation time* from known inputs.

| Function | Purpose |
|---|---|
| `slugify(s)` | ASCII-fold, lowercase, non-alphanumerics to a single `-`. `"Café Menu!"` → `"cafe-menu"`. |
| `uuid5(namespace, name)` | Name-based UUID, stable across machines and runs. |
| `sha256_hex(s)` | Hex SHA-256 of a string. |
| `hmac_sha256_hex(key, msg)` | Hex HMAC-SHA256. |
| `b64encode(s)` / `b64decode(s)` | Base64, over UTF-8 text. |
| `to_json(v)` | Canonical JSON: keys sorted, no insignificant whitespace, byte-stable — safe to hash or embed in a policy document. |
| `from_json(s)` | Parse JSON into plain data. |
| `merge(a, b, ...)` | Deep-merge dicts left to right, later winning; nested dicts merge recursively, other types are replaced. Arguments are not mutated. |

These functions operate on values, not `Ref`s. For values known only at apply,
use the [combinators](#output-combinators).

## Environments

```python
class AppEnv(EnvSchema):                 # annotated fields only
    domain: str
    size: int = 1

config = Config(AppEnv, envs={
    "dev":  {"region": "eu-north-1", "domain": "dev.example.io"},
    "prod": {"region": "us-east-1",  "domain": "example.io", "size": 5},
})
```

A `Config` declares every environment and its values, and is validated at
construction, so a missing or mistyped prod value fails `validate` rather than
the prod apply. `region`, `tags` and `name_prefix` are implicit in every schema,
so `Stack(env.name, config=env)` needs no `region=`.

`atlantide plan --env prod` narrows a run to one environment. The others are out
of scope, not undeclared, so their state is never planned for deletion. For
details, including the `var()` form, see
[Configuration](configuration.md#environments).

## Inputs and secrets

```python
build = atlantide.input("build", "local")   # a per-run value, with a default
key = atlantide.secret("signing-key")       # a handle to a stored secret
```

`atlantide.input()` reads a value supplied by `-var`, `--var-file` or
`[inputs]`. If an input has no default and is not supplied, the error names
all three sources. Determinism holds over *(config, inputs, selected
environments)*, and only inputs the config reads affect the result. See
[Configuration](configuration.md#inputs).

Values that differ between environments belong in a `Config`, which is checked
in and typed. Values that differ between runs of one environment are inputs.

`atlantide.secret()` returns a `SecretRef`, which is a name. Only the name
reaches the IR, the artifact and state; the plaintext is resolved in memory from
the secrets store at apply and redacted in plan output and logs. It does not
read from inputs, because a secret passed as an input would be written in
plaintext to all three.

Set the value with `atlantide secret set <name>`, and enforce secret handles
with [`require-secret-refs`](policies.md#require-secret-refs).

## Multi-account

AWS resources accept `provider_alias=`, which names an entry under
`[aws.aliases.*]` in `atlantide.toml`, to target another account:

```python
S3Bucket("assets", provider_alias="prod", ...)
```

The field is `immutable()`, so moving a resource between accounts is a replace,
not an update.

## What config may not do

Config is executed by Atlas-lang, not CPython. It has no clock, randomness,
environment, network or filesystem access.

Constructs outside the subset are rejected before evaluation, with the reason
and the alternative:

| Rejected | Because |
|---|---|
| `while` | Halting must be provable; use a bounded `for`. |
| `class` | Define resource types in a provider, not in config. One exception: a module-level [`EnvSchema`](configuration.md#the-schema) whose body is annotated fields only — no methods, decorators, metaclass or type parameters — which is a declaration, not a computation. |
| `try` / `raise` | No exceptions in config; guard with `if`. |
| `async` / `await` | Config is synchronous and pure. |
| `yield` | No generators; build lists with comprehensions. |
| `global` / `nonlocal` | No mutable module or closure state; pass arguments. |
| `:=` | Use a separate assignment. |
| `del` | Bound values are immutable. |

Imports are restricted to `atlantide.*`, so a vendored
[component](components.md) can be imported and `import os` cannot.

Bounded `for` loops, comprehensions, functions and conditionals are available.
Recursion is not rejected, but evaluation runs on a fuel budget, so a runaway
computation stops with `FuelExhaustedError` instead of hanging.

In summary: per-run values come from `atlantide.input()`, per-environment
values are declared in a [`Config`](configuration.md#environments), and code
that needs a real `class`, such as a [component](components.md) or a provider,
is ordinary Python outside the config.

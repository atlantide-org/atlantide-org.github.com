---
description: "Plan-time policies with enforce(): levels, narrowing by type, the built-in rules, and binding a policy to a resource type."
---

# Policies

A policy inspects one node's *pending change* and passes or fails it. Policies
run at plan time over the changeset, so a violation appears in the plan, before
any apply starts.

```python
from atlantide.policy import enforce

enforce("require-tags", keys=["env", "owner"])
enforce("deny-destroy-in-protected", stacks=["prod"])
enforce("require-secret-refs")
```

Call `enforce()` during config evaluation, conventionally at the top of the
file, outside any `Stack` block. Bindings are recorded in the IR and
round-trip through a `.atlas` artifact, so a plan built from an artifact
enforces the same policies as the config that produced it.

## Levels

```python
from atlantide.core import PolicyLevel

enforce("require-tags", keys=["env"], level=PolicyLevel.ADVISORY)
```

| Level | Effect of a violation |
|---|---|
| `MANDATORY` (default) | The plan is blocked. `plan` and `apply` exit `1`. |
| `ADVISORY` | Reported as a warning; the run proceeds. |

## Narrowing by type

`types=` restricts a binding to the named resource types. A single string is one
type name, not a sequence of characters:

```python
enforce("require-tags", types="aws.S3Bucket", keys=["owner"])
enforce("require-tags", types=["aws.S3Bucket", "aws.SqsQueue"], keys=["owner"])
```

A policy bound more than once is evaluated separately with each binding's
arguments, for example one `deny-destroy-in-protected` binding per environment.

## What a policy sees

Only **actionable** changes are evaluated; `NOOP` nodes are not passed to
policies. For each change the policy receives the node id, the pending action,
the stack, the desired resource and the binding's arguments. The desired
resource is `None` for a pure `DELETE`, so the built-in policies that inspect
the resource pass such nodes.

## Built-in policies

### `require-tags`

Requires the tag keys listed in `keys`. With no `keys`, requires only that the
resource has at least one tag.

```python
enforce("require-tags")                         # any tags
enforce("require-tags", keys=["env", "owner"])  # these keys
```

A key with an empty value counts as missing. Resource types without a `tags`
field are skipped.

### `require-secret-refs`

Every field marked sensitive must hold a `SecretRef` handle, not a literal.
Takes no arguments.

A secret referenced by name stays out of the config, the IR, state and the
`.atlas` artifact; a literal value is written to all four. A field declared with
`secret()` is typed `SecretRef | None`, so pydantic already rejects a literal.
This policy covers fields declared `mutable(..., sensitive=True)` on a plain
`str`, which accept plaintext without error.

### `deny-destroy-in-protected`

Denies destructive actions (`DELETE`, and the destroy half of a `REPLACE`) in
the stacks listed in `stacks`.

```python
enforce("deny-destroy-in-protected", stacks=["prod", "shared"])
```

With no `stacks`, it passes everything; there is no default protected stack.

`deny-destroy-in-prod` is an alias.

!!! note "Policy vs. `prevent_destroy`"
    `Lifecycle(prevent_destroy=True)` guards one resource and is checked by the
    planner. This policy guards every resource in a stack and is checked by the
    policy pass. They are independent; a resource can be covered by both.

## Argument errors

A binding with an argument the policy cannot use fails the plan with a
`PolicyConfigError` naming the policy and the parameter:

```
require-tags: `keys` must be a name or a list of them, got int
```

## Binding a policy to a resource type

Provider authors can attach a policy to a resource type so that every instance
carries it:

```python
from atlantide.policy import policy

@policy("require-tags")
class Gadget(AcmeResource):
    ...
```

The binding applies to that type only and is evaluated alongside the config's
`enforce()` bindings. Config cannot use the decorator, because Atlas-lang
accepts no classes other than an [`EnvSchema`](configuration.md#the-schema) of
annotated fields. It is an API for Python code: providers and the libraries
that publish [components](components.md).

## Where policies sit in the pipeline

Policy evaluation is the last step of stage 7, after the `prevent_destroy`
guard and after `--target`/`--replace` selection, so a policy sees the narrowed
changeset that would run. See
[How it works](../how-it-works/index.md#the-whole-pipeline-on-one-page).

---
description: "Components: grouping resources behind one object, publishing and consuming them with pinned commits, and worked examples."
---

# Components

A component groups several resources behind one parameterized object, like
Pulumi's `ComponentResource` or a CDK Construct. It turns a recurring piece of
architecture (a hardened bucket, a queue with its dead-letter queue, a service
and its role) into a single call.

Config can use components but cannot define them. Atlas-lang admits no `class`
with a body, except an [`EnvSchema`](configuration.md#the-schema) of annotated
fields, so a component is ordinary Python written by a library or provider
author:

```python
from atlantide.core import Component, child
from atlantide.providers.aws import S3Bucket

class SecureBucket(Component):
    def __init__(self, name, *, bucket):
        self.bucket = child(S3Bucket, "assets", bucket=bucket)
        # ...plus a TLS-only hardening policy wired to self.bucket
```

A component has no node of its own in the graph. Its children become ordinary
flat resources named `{component}-{child}`, so two instances of the same
component never collide.

## Publishing and consuming

Components are fetched once and pinned, as with `terraform init`. Config cannot
import from a live URL: it runs in a sandbox that may import only `atlantide.*`
and has no network access.

`component add` clones the source, records the resolved commit and a content
hash, and writes the tree into `.atlantis/`. Vendored code is imported under the
`atlantide.components.*` namespace, which the sandbox permits.

```bash
atlantide component add https://github.com/acme/secure-bucket --ref v1.2.0 --as acme --subdir src
atlantide component verify   # re-hash vendored trees vs the lock (tamper/drift)
atlantide component vendor   # rebuild .atlantis/ from the lock alone
atlantide component lock     # re-resolve declared refs -> commits
```

```python
from atlantide.components.acme import SecureBucket
SecureBucket("assets", bucket="acme-assets")
```

`add` records the source under `[components.acme]` in `atlantide.toml` and the
resolved pin in `atlantide.lock`. **Commit `atlantide.lock` and git-ignore
`.atlantis/`**, which is derived from it. A `build` artifact records each
component's commit as provenance.

## Worked examples

The atlantide-org organisation publishes two components. Each is a small
repository with its source in `src/` and tests covering the expansion, the diff
and the plan:

- **[aws-remote-state](https://github.com/atlantide-org/aws-remote-state)**: a
  versioned S3 bucket, a TLS-only bucket policy and a DynamoDB lock table, plus
  an optional access role and policy. This is the backend
  [remote state](remote-state.md) requires.
- **[aws-static-website](https://github.com/atlantide-org/aws-static-website)**:
  a private origin bucket, an origin access control, a CloudFront distribution
  and a bucket policy scoped to that distribution by `AWS:SourceArn`.

Both are added the same way. Pass a tag as `--ref`; `add` resolves it to a
commit:

```bash
atlantide component add https://github.com/atlantide-org/aws-remote-state \
  --ref <tag> --as acme --subdir src
```

**[component-template](https://github.com/atlantide-org/component-template)** is
a starting point for a new component, with the layout, CI workflow and test suite
in place, and a `scripts/rename.py` that renames the placeholder.

!!! warning "A published component is trusted code"
    Like a provider, a component runs with the same access as the engine. Review
    it before adding it. After that, integrity rests on the pin: `verify`
    re-hashes every vendored tree and fails on any tampering or drift.

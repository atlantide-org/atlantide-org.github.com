---
description: "The local, random and aws providers, their resource types and defaults, data sources, and writing a provider plugin."
---

# Providers

Atlantide ships with three providers.

**`local`**: `File`, `SourceFile` and `Null`. Requires no credentials and runs
anywhere, including CI.

**`random`**: `Uuid`, `Password`, `Id` and `Timestamp`. Each value is generated
once at apply and pinned in state; re-applying does not regenerate it.

**`aws`**: the resource types below, the `AwsCallerIdentity` and
`AwsAvailabilityZones` data sources, the IAM policy helpers (`allow`, `deny`,
`assume_role`, `ServicePrincipal`), and the `SecureBucket` component. Any resource
can set `provider_alias=` to target an alternate account.

| Area | Types |
| --- | --- |
| Storage | `S3Bucket`, `S3BucketPolicy`, `S3Folder` |
| Messaging | `SqsQueue`, `SnsTopic`, `SnsSubscription` |
| Compute | `LambdaFunction` |
| Identity | `IamRole`, `IamPolicy` |
| Data | `DynamoDbTable` |
| Observability | `CloudWatchLogGroup` |
| Networking | `Vpc`, `Subnet`, `SecurityGroup`, `InternetGateway`, `ElasticIp`, `NatGateway`, `RouteTable` |
| Edge and DNS | `CloudFrontDistribution`, `OriginAccessControl`, `AcmCertificate`, `Route53HostedZone`, `Route53Record` |

## Defaults

**`S3Bucket` blocks public access and enables SSE-S3 encryption by default.**
Set `force_destroy=True` to empty the bucket (objects, versions and delete
markers) before removing it. Without it, S3 refuses to delete a non-empty bucket
and teardown stalls.

**`SecurityGroup` egress defaults to allow-all**, matching the AWS default. Pass
`egress=[]` to revoke it.

**`Subnet` requires an `availability_zone`.** Take it from
`AwsAvailabilityZones` instead of a literal; available zone letters differ
between accounts.

**`CloudFrontDistribution` accepts `aliases` and `certificate_arn`**, and
`Route53Record` accepts an `alias` target. Together they allow serving an apex
domain from CloudFront.

**`LambdaFunction` requires a package.** Set `code_path=` to a local zip or
directory, or set `s3_bucket=` and `s3_key=` for an uploaded package. A directory
is zipped with sorted entries and fixed timestamps, then fingerprinted into
`code_sha256` at config-evaluation time. Two checkouts of the same source produce
the same digest; editing the source produces a planned update.

## Data sources

A data source reads a fact about the account instead of hardcoding it, so one
config can run against multiple accounts:

```python
from atlantide.providers.aws import AwsAvailabilityZones, AwsCallerIdentity

me = AwsCallerIdentity("me")
zones = AwsAvailabilityZones("azs")
```

Each is read once at apply and pinned in state. A plan makes no provider call,
and two runs of the same config produce identical IR.

Data sources are never destroyed. `destroy` drops the state entry without
calling the provider, because atlantide did not create the object being read.

## Writing a provider

A provider is a Python package that declares one entry point:

```toml
[project.entry-points."atlantide.providers"]
acme = "acme_atlantide:PLUGIN"
```

```python
from atlantide.core.plugin import ProviderPlugin

PLUGIN = ProviderPlugin(
    name="acme",
    types={Gadget.type_name(): Gadget},
    factory=lambda settings: AcmeProvider(**settings),
    module="acme_atlantide",       # what config is allowed to import
)
```

Once installed, `atlantide providers` lists it and config can use
`from acme_atlantide import Gadget`.

`factory` receives the provider's `[provider.<name>]` settings as a raw mapping,
so a third-party provider can accept options atlantide does not define.

A plugin that fails to load is reported and does not block unrelated commands.
`--no-plugins` ignores all installed plugins, for reproducing a build or
bisecting a plugin that breaks a run.

!!! warning "A plugin is trusted code"
    A plugin runs in the same process, with the same access as atlantide.
    Atlas-lang sandboxes a malicious *config*, not a malicious *plugin*. Treat
    installing a plugin like installing any other dependency.

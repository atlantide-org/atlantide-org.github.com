---
description: "S3+DynamoDB and Postgres state backends, lease-based locking and concurrency, state management commands, and remote secrets."
---

# Remote state

State defaults to a local SQLite file, usable from one machine only. Set `[state]`
to a shared backend to use the same commands from a team or a CI runner.

```toml
[state]
backend    = "s3"                      # "local" (default) | "s3" | "postgres"
bucket     = "acme-atlantide-state"
key        = "prod/atlantide.json"
lock_table = "atlantide-locks"         # DynamoDB table, hash key `node_id` (S)
region     = "eu-north-1"
kms_key_id = "alias/atlantide"         # optional; SSE-S3 (AES256) otherwise

lock_ttl            = 300              # seconds a lease lasts before it lapses
lock_renew_interval = 100              # how often a live run pushes that out
```

```toml
[state]
backend = "postgres"                   # needs the extra: pip install atlantide[postgres]
dsn     = "postgresql://…"             # or the ATLANTIDE_STATE_DSN env var
schema  = "atlantide"
```

## Concurrency

Locks are held per node id, not over the whole store. Apply re-diffs after
acquiring the lease, and actions can appear or disappear between the two diffs,
so the lease covers the whole desired graph plus everything already recorded in
state.

**Two applies run concurrently only if both their configs and their prior state
are disjoint.** Two applies over the same stack serialize.

A run that loses its lease (the hold lapsed and another run claimed it) stops and
reports it. It does not roll back: a compensation is a state write, and the lease
no longer authorises one. Run `atlantide refresh` to recover.

### Preparing the backend

Atlantide does not create the bucket or the lock table. They are the trust root
for shared state and must exist before first use, configured with:

- **Bucket versioning**, to recover from a bad state write.
- **A DynamoDB TTL on `expires_at`**, so abandoned leases expire.

`state check` verifies this setup in one pass. It also probes whether the
endpoint honours conditional writes; an S3-compatible store that accepts the
request but ignores the condition defeats every compare-and-swap the backend
relies on.

```bash
atlantide state check              # --no-probe skips the scratch write
```

## Managing state

```bash
atlantide state list                     # every recorded resource
atlantide state show <id>                # one resource's stored inputs and outputs
atlantide state rm <id>                  # forget a row without destroying anything

atlantide state backup                   # ./atlantide-state-<serial>-<ts>.atlas-state
atlantide state restore snap.atlas-state
atlantide state migrate --from atlantide.db      # local -> remote
atlantide state migrate --to-local atlantide.db  # remote -> local

atlantide state unlock                           # who holds what
atlantide state unlock --owner ci-runner-7 -y    # break a dead run's holds
```

**`backup` and `restore`** run under the state lock, so a snapshot cannot capture
part of a concurrent apply. `restore` previews which nodes it will stop tracking,
and refuses a snapshot if state has been written since it was taken, unless
given `--force`. It rewrites only atlantide's record, not cloud resources, so
restoring an old snapshot creates drift.

**`state rm`** removes a row that no longer describes a real resource. It does
not call the provider. If the resource still exists, it becomes untracked and the
next apply creates a second one. The command snapshots state first and reports
the snapshot.

**`state migrate`** copies in a single write in either direction, so an
interrupted migration cannot leave a partially populated destination.

!!! note "Upgrading a shared backend"
    The schema is versioned and migrates forward automatically. Take a snapshot
    first, and upgrade every machine sharing the backend at the same time. An
    older atlantide refuses a newer store rather than misreading it.

## Secrets

Secret *values* can come from a remote store. Config, the IR and state hold only
the secret's name:

```toml
[secrets]
provider = "ssm"                       # "keyfile" (default) | "env" | "ssm"
prefix   = "/atlantide/prod/"          # secret `db_password` -> /atlantide/prod/db_password
region   = "eu-north-1"
```

!!! warning "Point `secrets_key` at a shared path when state is shared"
    The keyfile encrypts the local value store, salts the rotation digests, and
    seals sensitive outputs at rest.

    A teammate without the keyfile cannot unseal those outputs and sees every
    secret field as rotated. `plan` detects this pattern (every secret in state
    mismatching, none intact) and warns instead of listing spurious updates.
    KMS-backed keys are not supported.

---
description: "The two-phase Merkle hash in detail: what goes into input_hash, symbolic refs, and why unchanged subgraphs cost no provider calls."
---

# The Merkle hash

The `input_hash` makes a re-run free of provider calls, propagates a change to
exactly the affected nodes, and lets `plan` run without credentials.

The [walkthrough](walkthrough.md) reaches this point at step 6, once the graph
has been built.

---

## The definition

From [`ir/merkle.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/ir/merkle.py):

```
h(n) = sha256( canonical({ type, properties, [h(d) for d in sorted(deps(n))] }) )
```

The implementation
([`ir/merkle.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/ir/merkle.py)):

```python
def merkle_hashes(ir: IRGraph, topo_order: Sequence[str]) -> dict[str, str]:
    by_id = {node.id: node for node in ir.nodes}
    hashes: dict[str, str] = {}
    for node_id in topo_order:
        node = by_id[node_id]
        ignored = set(node.ignore_changes)
        properties = (
            {k: v for k, v in node.properties.items() if k not in ignored}
            if ignored else node.properties
        )
        payload = {
            "type": node.type,
            "properties": properties,
            "deps": [hashes[dep] for dep in sorted(node.dependencies)],
        }
        hashes[node_id] = hashlib.sha256(to_canonical_json(payload)).hexdigest()
    return hashes
```

Four details of the function:

| Detail | Why |
|---|---|
| **Iterated in `topo_order`** | Guarantees `hashes[dep]` is already computed when a node needs it. The Kahn ordering therefore runs first, and a cycle is a hard error — a cyclic graph has no fixpoint for this recursion. |
| **`sorted(node.dependencies)`** | Only the dependency *set* affects the hash, not its order, so reordering config does not register as a change. |
| **`to_canonical_json`** | RFC 8785. Key order, number format and string escaping are fixed, so the same logical payload always produces the same bytes on any machine, any Python version. |
| **`ignore_changes` fields removed before hashing** | A field listed in `ignore_changes` cannot move the hash, so it never triggers an UPDATE or REPLACE. The diff drops the same fields, so the two agree. |

## It is a DAG fold, not a classic Merkle tree

A classic Merkle tree is a binary tree over a list, built so that membership of
one leaf can be proved with O(log n) sibling hashes. None of that applies here:
there are no sibling proofs, no root hash used for verification, and no balanced
structure.

Only the recursive-hash property is borrowed: a node's hash is a function of its
own content plus its children's hashes, so any change propagates to every
ancestor. Here the structure is the resource DAG, "children" are dependencies,
and there is one hash per node rather than a single root.

The root-hash role ("did the whole config change?") is filled separately by
`ir_hash` over the entire IR
([step 5](walkthrough.md#5-stage-3-canonicalize-and-hash)).

The structure is a *content-addressed dependency graph*.

## Watch the ripple, with real numbers

Same two-resource config, hashed under three variants:

- **A** baseline — `path="out/greeting.txt"`, `content="hello atlantide"`
- **B** mutable change — `content="hello world"`
- **C** immutable change — `path="out/hello.txt"`

```
demo:local.File:greeting
   A  baseline            a0de4c9548771eba8f0e405ce45cd5abeeee898994db49a334c208b831e9f9bd
   B  mutable change      6c1673dc289138d0a7ddb87bebc280c85492b5bca8cd936863c5010d775a40c2
   C  immutable change    01d15e92cad556ebb9279d3c30c84dc5f4042157ea3bd4830ecebb251be4975b

demo:local.File:receipt
   A  baseline            d1c54122b306e5ee15c79032364658d9151835a7e7ace777b65ba7b36715862a
   B  mutable change      eae4a250263c2385c2c58f1301f12d2f27bf8fc65bd0293cd0e6f55e0908bbf8
   C  immutable change    ab516e29d39b2760d74f40ec1972efd8602dab6d1b23ffdfa0888054cba5f84b
```

`receipt`'s hash changes in all three variants, although `receipt` was never
edited. Its own properties are byte-identical across all three:

```
receipt's OWN properties, per variant (canonical bytes):
   A  {"content":{"$ref":"demo:local.File:greeting#checksum"},"path":"out/receipt.txt"}
   B  {"content":{"$ref":"demo:local.File:greeting#checksum"},"path":"out/receipt.txt"}
   C  {"content":{"$ref":"demo:local.File:greeting#checksum"},"path":"out/receipt.txt"}
```

The difference is entirely in the `deps` entry. The payload hashed for `receipt`
under variant A:

```json
{
  "type": "local.File",
  "properties": {
    "path": "out/receipt.txt",
    "content": { "$ref": "demo:local.File:greeting#checksum" }
  },
  "deps": [
    "a0de4c9548771eba8f0e405ce45cd5abeeee898994db49a334c208b831e9f9bd"
  ]
}
```

canonicalized:

```
{"deps":["a0de4c95…f9bd"],"properties":{"content":{"$ref":"demo:local.File:greeting#checksum"},"path":"out/receipt.txt"},"type":"local.File"}
sha256 -> d1c54122b306e5ee15c79032364658d9151835a7e7ace777b65ba7b36715862a
```

and under variant B, the identical payload with one substitution:

```json
  "deps": [
    "6c1673dc289138d0a7ddb87bebc280c85492b5bca8cd936863c5010d775a40c2"
  ]
```

That field is the whole mechanism. It explains the plan output at
[step 10 of the walkthrough](walkthrough.md#10-update-vs-replace-per-field-mutability),
where `receipt` shows `~ update` with an identical `$ref` on both sides of the
arrow: the CLI renders the properties, which did not change, while the diff
reacts to the `deps` entry, which did.

## Why the hash is computed over *symbolic* refs

`properties` keeps `{"$ref": "demo:local.File:greeting#checksum"}` rather than the
resolved checksum. Three consequences follow:

1. **No provider I/O is needed to compute the hash.** The resolved value of that
   ref does not exist until `greeting` has been created. If the hash depended on
   resolved values, `plan` would need to call the provider, and therefore need
   credentials.
2. **Nothing is lost.** A ref's resolved value can only change if the referenced
   node changed, and that is already folded in via `deps`. An unchanged hash
   therefore implies unchanged resolved inputs.
3. **The hash the executor persists equals the hash the planner computed**
   ([`reconcile/executor.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/reconcile/executor.py)),
   because both are over the symbolic form. No apply-time recompute step can
   disagree with the plan.

## How the diff uses it

In [`reconcile/diff.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/reconcile/diff.py):

```python
if desired_hashes[node_id] == have.input_hash:  # Merkle skip: no provider read
    return Change(node_id, Action.NOOP, desired=want, prior=have)
return _classify(want, have, mutability.get(want.type, {}))
```

The full ladder in `_change_for` ([`reconcile/diff.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/reconcile/diff.py)):

| Condition | Action |
|---|---|
| in prior state only | DELETE |
| in desired IR only | CREATE |
| in both, but `status != created` (a write-ahead row from a crashed create) | CREATE — never NOOP |
| in both, **hashes equal** | **NOOP — no provider `read`, no provider anything** |
| in both, hashes differ | `_classify` → per-field mutability decides UPDATE vs REPLACE |

A no-op does not mean "checked and matched"; it means "not checked". This is the
source of the performance gain and of the limitation described at
[step 11 of the walkthrough](walkthrough.md#11-drift-and-the-limit-of-the-model).

When hashes differ, `_classify` needs a set of changed fields. Usually a property
comparison supplies it. In the propagation case the properties are identical, so
[`_changed_fields`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/reconcile/diff.py)
attributes the change to the ref-bearing fields, whose resolved values are what
moved. This is why the plan names `content` on `receipt`.

## Two cases the hash alone cannot see

The Merkle hash is a function of the config alone. Two situations change a node's
real inputs without changing its hash; each has its own mechanism.

**1. An upstream node is recreated for a *state-side* reason.** Suppose
`greeting` is missing from state, or its create never confirmed. Its config is
unchanged, so its hash and `receipt`'s hash are unchanged, yet `greeting` is
about to get a new physical identity and `receipt`'s resolved input will change. `_stale_dependents`
([`reconcile/diff.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/reconcile/diff.py)) pulls
those NOOPs back into the changeset, transitively, whenever an upstream action is
CREATE or REPLACE.

**2. A state row stops being trustworthy.** If a rollback compensation calls the
provider and then dies before writing state, the stored row describes something
that no longer exists. Because the diff is symbolic, its stored hash still
matches config, and the next plan would report NOOP indefinitely. The sentinel
`NO_INPUT_HASH` is written into `input_hash` so the comparison can never succeed. Both `_poison`
([`reconcile/executor.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/reconcile/executor.py))
and `refresh --write` ([`reconcile/refresh.py`](https://github.com/atlantide-org/atlantide/blob/main/atlantide/reconcile/refresh.py))
use it. `_poison` writes it *before* running the compensation; otherwise a
process killed mid-rollback would leave the row clean and the divergence silent.

A poisoned row is classified as UPDATE, not REPLACE. `_changed_fields` checks
`prior.input_hash != NO_INPUT_HASH` before attributing the change to ref-bearing
fields, because a ref-bearing field can also be `immutable()`
(`SecurityGroup.vpc_id`, `Route53Record.zone_id`). Attributing a change there
would turn "re-check this node" into "destroy and recreate working
infrastructure".

## Reproduce the numbers

The hashes above were produced by calling the pure stages directly:

```python
from atlantide.graph.build import build_graph
from atlantide.graph.order import topological_order
from atlantide.ir.lower import lower
from atlantide.ir.merkle import merkle_hashes
from atlantide.lang import evaluate_source

registry = evaluate_source(open("infra.py").read()).unwrap()
ir = lower(registry)
graph = build_graph(ir).unwrap()
print(merkle_hashes(ir, topological_order(graph)))
```

It needs no credentials, state file or network access.

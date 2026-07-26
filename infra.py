"""Your first Atlantide config.

Valid Python -- editors, formatters and type checkers read it -- but executed by
Atlas-lang, a bounded interpreter with no clock, randomness, environment or
network. The same config always produces the same plan, and the engine relies on
that: an unchanged config hashes identically, so re-applying calls no provider.

    atlantide validate     # syntax, the language subset, and the graph
    atlantide plan         # what would change
    atlantide apply        # reconcile
    atlantide plan         # again: no changes
    atlantide destroy

`atlantide resources` lists every type this install can see, and
`atlantide schema local.File` prints one type's fields.

This starter uses the `local` provider, so it needs no cloud credentials.
Run `atlantide init --template aws` for an AWS starter instead.
"""

from atlantide.core import Stack, output
from atlantide.providers.local import File

# A Stack scopes region, tags and name_prefix over everything in its body. The
# local File has no region field and simply ignores it.
with Stack("dev", region="eu-north-1", tags={"env": "dev"}):
    greeting = File(
        "greeting",
        path="build/hello.txt",
        content="hello from atlantide\n",
    )

    # Reading a computed field returns a lazy reference rather than a value. That
    # is what wires a dependency edge -- no depends_on, no string addresses -- and
    # it resolves to the real checksum at apply.
    output("greeting_checksum", greeting.checksum)

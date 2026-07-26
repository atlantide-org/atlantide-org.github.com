---
description: "Install the standalone binary or the PyPI package, scaffold a project with atlantide init, and upgrade or remove Atlantide."
---

# Installation

Atlantide is distributed as a standalone binary that bundles its own Python
runtime, and as a package on PyPI.

| | Standalone binary | PyPI package |
| --- | --- | --- |
| Python needed | no | 3.12 or newer |
| Providers available | the three built-in ones only | built-in **and** third-party plugins |
| Use it for | CI images, machines without Python, quick trials | anything using a provider plugin, or embedding the engine |

See [provider plugins](#provider-plugins-and-the-binary) for the provider
difference.

---

## Standalone binary

Each release publishes binaries for three platforms on the
[releases page](https://github.com/atlantide-org/atlantide/releases). Each is a
single executable of about 30 MB with no external dependencies.

=== "Linux (x86-64)"

    ```bash
    curl -L -o atlantide \
      https://github.com/atlantide-org/atlantide/releases/latest/download/atlantide-linux-x86_64
    chmod +x atlantide
    sudo mv atlantide /usr/local/bin/
    ```

    The binary is built on the current Ubuntu runner image and links against its
    glibc. On older distributions, install from PyPI.

=== "macOS (Apple silicon)"

    ```bash
    curl -L -o atlantide \
      https://github.com/atlantide-org/atlantide/releases/latest/download/atlantide-macos-arm64
    chmod +x atlantide
    xattr -d com.apple.quarantine atlantide
    sudo mv atlantide /usr/local/bin/
    ```

    !!! warning "macOS blocks the binary until the quarantine flag is cleared"
        The published binaries are not code-signed or notarised. macOS adds a
        quarantine attribute to downloaded files, and Gatekeeper refuses to run an
        unsigned executable that carries it, reporting that the developer cannot be
        verified.

        The `xattr -d com.apple.quarantine` line above removes the attribute.
        Alternatively, open the file once from Finder with right-click → Open and
        confirm the prompt.

=== "Windows (x86-64)"

    ```powershell
    curl.exe -L -o atlantide.exe `
      https://github.com/atlantide-org/atlantide/releases/latest/download/atlantide-windows-x86_64.exe
    ```

    Move `atlantide.exe` to a directory on your `PATH`.

### Confirm it runs

```bash
atlantide --version
```

```
atlantide 0.x.y
```

### Provider plugins and the binary

Providers are discovered through the `atlantide.providers` entry-point group, so
they must be installed alongside atlantide as Python distributions. The standalone
binary has no site-packages, advertises no entry points, and uses only the
providers compiled into it:

```console
$ atlantide providers
                                 3 provider(s)
┏━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ name   ┃ types ┃ module                     ┃ summary                        ┃
┡━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ aws    │    25 │ atlantide.providers.aws    │ AWS resources over boto3.      │
│ local  │     3 │ atlantide.providers.local  │ Files and no-ops on the local  │
│        │       │                            │ machine; needs no credentials. │
│ random │     4 │ atlantide.providers.random │ Values generated once at apply │
│        │       │                            │ and pinned in state.           │
└────────┴───────┴────────────────────────────┴────────────────────────────────┘
```

If a config imports a third-party provider, install from PyPI. With the binary,
the failure appears as config being unable to find the provider's types, not as a
missing plugin.

---

## From PyPI

Requires Python 3.12 or newer.

```bash
uv tool install atlantide     # standalone CLI, isolated environment
pipx install atlantide        # the same, via pipx

uv add atlantide              # into a project
pip install atlantide         # into the current environment
```

For the CLI alone, use `uv tool install` or `pipx`; both install atlantide and its
dependencies in an isolated environment.

Use `uv add` or `pip install` when embedding the engine as a library, or when a
config imports a provider plugin. A plugin must resolve in the same environment as
atlantide.

### Extras

The Postgres state backend requires an extra, which installs a database driver:

```bash
pip install 'atlantide[postgres]'
```

The sqlite and S3 backends need nothing beyond the base install.

---

## Building the binary yourself

Build the binary yourself for a platform with no published asset, or to pin it to
a specific commit:

```bash
git clone https://github.com/atlantide-org/atlantide
cd atlantide
make binary          # uv run --extra build pyinstaller atlantide.spec --clean --noconfirm
```

The executable is written to `dist/atlantide`. It bundles whatever is installed
in the build environment, so this is also how to produce a binary that includes a
provider plugin or the Postgres driver.

---

## Verifying an installation

```bash
atlantide --version      # the version, and that the executable runs at all
atlantide providers      # which providers this installation can see
```

`atlantide providers` also lists any plugin that failed to load. Otherwise, a
failed plugin is only visible as config being unable to find its types.

To confirm an end-to-end setup without credentials or an AWS account, follow the
[walkthrough](how-it-works/walkthrough.md). It uses the `local` provider and
creates only files on disk.

---

## Upgrading and removing

```bash
uv tool upgrade atlantide     &&  uv tool uninstall atlantide
pipx upgrade atlantide        &&  pipx uninstall atlantide
pip install --upgrade atlantide  &&  pip uninstall atlantide
```

To upgrade a standalone binary, download the new release over the old file and
check it with `atlantide --version`.

Upgrading does not modify state. When a newer atlantide opens a store, it migrates
it forward automatically; an older atlantide refuses to read a newer store.
Upgrade every machine that shares a backend at the same time. See
[Managing state](reference/remote-state.md#managing-state).

---

## Scaffolding a project

`atlantide init` writes `atlantide.toml`, a starter config and a `.gitignore`,
then compiles the result before reporting success:

```bash
atlantide init                        # `minimal` template, local state
atlantide init --template aws         # an AWS starter instead
atlantide init --state s3 --bucket acme-atlantide-state \
               --key prod/atlantide.json --lock-table atlantide-locks
```

| Option | Values |
| --- | --- |
| `--template` | `minimal` or `aws` |
| `--state` | `local`, `s3` or `postgres`; writes the matching `[state]` table |
| `--bucket`, `--key`, `--lock-table` | s3 state settings |
| `--dsn`, `--schema` | postgres state settings |
| `--secrets` | `keyfile`, `env` or `ssm` |
| `--force` | allow overwriting existing files or nesting inside another project; refused otherwise |

The `minimal` template needs no credentials; see the
[quickstart](index.md#quickstart).

---

## Next steps

- **[How it works](how-it-works/index.md)** — the mental model, then a
  walkthrough that needs no AWS account.
- **[Building on AWS](aws/index.md)** — a multi-environment stack built one
  resource at a time.
- **[CLI](reference/cli.md)** — every command and flag.

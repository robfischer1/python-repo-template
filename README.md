# python-repo-template

A [copier](https://copier.readthedocs.io) template that scaffolds a standard,
container-ready Forge Python project — either a FastMCP constellation service
or a plain library/CLI, your choice at scaffold time. Realizes the Forge
service-repo standard (`furnace/docs/service-repo-standard.md`). This repo is
the template only — it generates other repos, it does not run as a service
itself. Pure code; the AI/governance layer (`.claude/`, `AGENTS.md`) is poured
into the generated repo separately by `furnace ignite` (decoupled by design).

## Use

```bash
copier copy gh:robfischer1/python-repo-template my-new-service
# or from a local checkout:
copier copy /path/to/python-repo-template my-new-service
```

Copier asks a set of questions (see below), then runs `_tasks`: `git init`,
wire the remotes (`origin` = the Ourea door, `forgejo` fetch-only, `github` the
push mirror — see [Remotes](#remotes)), `uv sync`, generate `.secrets.baseline`,
install pre-commit hooks, run `specify init` (spec-kit scaffold), and finally
`furnace ignite . --kit code-repo-sdd` to pour the governance layer. A failure
in any task rolls back the whole stamp — there is no half-scaffolded repo.

### Update an existing generated repo

```bash
cd my-new-service
copier update      # 3-way merges template changes, preserving local edits
```

`uv lock` re-runs on every `update` (not just `copy`) so a template change to
`pyproject.toml` never leaves a stale `uv.lock` that the admission gate's
`uv sync --locked` would reject.

## Questions asked

| Question | Type | Default | Notes |
| :-- | :-- | :-- | :-- |
| `project_name` | str | — | Human-readable name |
| `package_name` | str | slug of `project_name` | Importable package (snake_case) |
| `service_name` | str | slug of `project_name` | Repo/image/console-script name (kebab-case) |
| `description` | str | "A standard Forge Python project." | One-liner |
| `mcp` | bool | `true` | FastMCP service shape vs. plain library/CLI |
| `core_backed` | bool | `false` | Builds FROM `mnemosyne-core-base` (constellation stars only); asked when `mcp` |
| `core_base_tag` / `core_version` | str | `v0.1.0` / `v0.2.0` | Pins when `core_backed` |
| `sovereign_database` | bool | `false` | Star owns its own Postgres (chaos pattern); asked when `mcp` |
| `db_kind` | str | `postgres` | `postgres` or `pgvector`; asked when `sovereign_database` |
| `port` | int | `8000` | streamable-HTTP listen port; asked when `mcp` |
| `author_name` / `year` | str / int | "Rob Fischer" / 2026 | Copyright |
| `charter` | str | `description` | Single-responsibility charter (<=100 chars) for `star.toml` |
| `cluster` | str | `pantheon` | Constellation cluster |
| `star_namespace` | str | `package_name` | Sovereign namespace for `star.toml` |
| `substrate_kind` | str | `container` | Deployment substrate |
| `interstellar` | bool | `false` | Adds `async = ["kafka"]` to `star.toml` |

## What you get (rendered repo)

- PyPA `src/` layout, PEP 621 `pyproject.toml` (hatchling), single-sourced
  version from `__init__.py`
- If `mcp`: a minimal FastMCP streamable-HTTP server (`server.py`, stateless,
  config-via-env), a `ping` tool, an async heartbeat publisher to Pontus
  (`heartbeat.py`, optional `kafka` extra), a multi-stage non-root Dockerfile,
  `.dockerignore`, and a Compose stack (shape depends on `core_backed` /
  `sovereign_database`)
- Born-with operational surface: `health.py` (the `{live, ready, metrics}`
  op-contract from `stellar_core`), `observability.py` (OTLP wiring to
  Hemera), `oneiroi.py` (memory-emission stub)
- A born-conformant `star.toml` — the constellation `StarManifest` every
  admission gate reads
- Lint/type/test baseline: ruff (`select=ALL`), mypy strict, pyright strict,
  pytest with coverage
- Forgejo Actions: `ci.yml` (PR gate: lint/type/test + pip-audit + opengrep
  SAST), `admit.yml` (constellation admission: cosign verify, syft SBOM, local
  `opa eval` against the signed policy authority), and — when `mcp` —
  `deploy.yml` (build/scan/sign/push on merge to `main`)
- The community publish-set: README, LICENSE (Apache-2.0), CONTRIBUTING,
  SECURITY, CODE_OF_CONDUCT, CHANGELOG
- A vendored opengrep taint ruleset (`rules/sast/dataflow.yml`) for SSRF/SQLi
  data-flow checks that ruff's AST-level `S` rules can't express

## Structure

```
copier.yml                    # questions + _tasks (git init, uv sync, furnace ignite, ...)
template/                      # _subdirectory — everything below is rendered into the new repo
  pyproject.toml.jinja
  star.toml.jinja
  README.md.jinja / CONTRIBUTING.md.jinja / CHANGELOG.md.jinja / LICENSE.jinja
  cosign.pub                    # constellation public key (unconditional)
  {% if core_backed %}cosign.pub{% endif %}   # same key, gated copy (see CLAUDE-INIT.md)
  .forgejo/workflows/{ci.yml, admit.yml, {% if mcp %}deploy.yml{% endif %}.jinja}
  .forgejo/versions.env         # pinned tool versions shared by admit.yml + deploy.yml
  rules/sast/dataflow.yml       # opengrep taint rules
  src/{{package_name}}/
    __init__.py.jinja  settings.py.jinja  health.py.jinja
    heartbeat.py.jinja  observability.py.jinja  oneiroi.py.jinja
    {% if mcp %}server.py{% endif %}.jinja
  tests/test_smoke.py.jinja
```

## Remotes

A stamped repo is born with three remotes, the post-F27 fleet convention:

| Remote | URL | Role |
|---|---|---|
| `origin` | `https://git.notusmi.com/<service_name>.git` | The **Ourea door** — the authoritative git gateway. Serves real fetch/pull, and gates landings via `Serves`. Takes a **bare** repo name, no `rob/` prefix. |
| `forgejo` | `https://forgejo.notusmi.com/rob/<service_name>.git` | **Fetch only.** Its push side is set to the `no_push_f27` sentinel so a stray `git push forgejo` fails loudly instead of bypassing the gate. |
| `github` | `https://github.com/robfischer1/<service_name>.git` | Push mirror. |

The remote repo must still be created on Forgejo first — push-to-create is
disabled instance-wide. The `_tasks` only wire the local remotes.

## Development (of the template itself)

This repo has no `pyproject.toml` of its own, but it **is** gated. Every PR runs
the render matrix declared in `ci-matrix.toml` through the canonical
`template-ci.yml` in `foundry/foundry-stocks` — each answer combination is
rendered, its expected file set asserted, and every rendered `.toml`/`.json`
parsed. Adding a variant means adding a `[[case]]` there, not touching a
workflow.

To reproduce the gate locally:

```bash
python3 /path/to/foundry-stocks/ci/lib/template_render_matrix.py --template .
```

It renders with `--trust --skip-tasks --vcs-ref=HEAD`, so no task runs (no
`git init`, no `uv sync`, no `furnace ignite`) and it renders **your working
commit** rather than the newest tag — copier resolves a git template to its
latest tag by default, which would otherwise gate the last release instead of
your change.

For a full-fidelity check the matrix does not cover — that a stamp actually
builds — render one for real and run its gate:

```bash
copier copy --trust . /tmp/smoke-test --data project_name="Smoke Test" --defaults
cd /tmp/smoke-test && uv sync --extra dev && uv run pytest
```

## Fleet role

Genesis point for every new Forge Python repo — plain library/CLI or
constellation MCP star. Copier owns repo creation (this template); `furnace`
owns the `.claude/` AI-governance layer, poured by the final `_task`
(`furnace ignite . --kit code-repo-sdd`). See
`furnace/docs/service-repo-standard.md` for the standard this template
realizes.

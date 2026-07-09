Codebase orientation for AI sessions. Posture and governance live in
AGENTS.md (furnace-compiled); this file is the repo-specific map, read on
demand.

## Overview

`python-repo-template` is a **copier template**, not a runnable project. It
has no `pyproject.toml`, no source package, no tests of its own at the repo
root — everything that looks like Python/Docker/CI config lives under
`template/` and is Jinja-rendered into a *new* repo by `copier copy`. Rob
runs `copier copy gh:robfischer1/python-repo-template <new-repo>`, answers
the prompts in `copier.yml`, and gets back either:

- a **FastMCP constellation star** (`mcp: true`, the default) — a
  streamable-HTTP MCP service with the born-with op-contract, heartbeat,
  Dockerfile, Compose stack, and `star.toml`; or
- a **plain Python library/CLI** (`mcp: false`) — same QA/CI/lint spine, no
  service machinery.

Role in the fleet: this is the genesis point for every new Forge Python
repo. It lays the pure-code body; the final `_task` hands off to `furnace
ignite` to pour the `.claude/` AI-governance layer. Copier owns repo
creation; furnace owns governance — deliberately decoupled (see the header
comment block in `copier.yml`).

**When editing this repo**, you are editing the *generator*, not a service.
There is nothing to `uv sync` or `pytest` here directly — see Build/Test/Run
below for how to actually validate a change.

## Architecture / module map

```
copier.yml            # Questions (project_name, package_name, service_name,
                       # mcp, core_backed, sovereign_database, db_kind, port,
                       # charter, cluster, star_namespace, substrate_kind,
                       # interstellar, author_name, year) + _tasks (post-copy
                       # setup pipeline, see below).
README.md              # This template repo's own user-facing doc.
template/               # _subdirectory in copier.yml — the tree that gets
                        # rendered. Every path under here can itself contain
                        # Jinja in the FILENAME (conditional files/dirs) as
                        # well as in file CONTENT (.jinja suffix).
```

Inside `template/`:

- **`pyproject.toml.jinja`** — PEP 621 project, hatchling build backend,
  version single-sourced from `src/{{package_name}}/__init__.py`. Carries
  the canonical Forge lint/type/test policy: ruff `select = ["ALL"]` with a
  documented ignore list, mypy strict, pyright strict, pytest+coverage. Adds
  `mcp[cli]` when `mcp`, `mnemosyne-core` when `core_backed`, `psycopg`/
  `pgvector` extras when `sovereign_database`. Resolves `stellar-core` from
  a private Forgejo PyPI index (`[[tool.uv.index]]`).
- **`star.toml.jinja`** — the constellation `StarManifest` (validated by
  `constellation.manifest.StarManifest`, a pydantic model in the sibling
  `constellation` repo). Every stamped repo is a *candidate star*; `admit.yml`
  reads this at PR time. Carries `[governance].bundle/tag/digest` — the
  cosign-signed policy pin that Renovate bumps.
- **`src/{{package_name}}/`** — the package skeleton (directory name is
  itself Jinja, rendered from the `package_name` answer):
  - `__init__.py.jinja` — `__version__ = "0.1.0"` (single source for hatch).
  - `settings.py.jinja` — `pydantic_settings.BaseSettings`, env-prefixed
    `{PACKAGE_NAME}_`. Adds `host`/`port`/`kafka_bootstrap`/`heartbeat_topic`
    when `mcp`.
  - `health.py.jinja` — the born-with `{live, ready, metrics}` op-contract
    from the `stellar_core` SDK. `McpOpsAdapter` when `mcp`, else
    `HttpOpsAdapter` (z-pages). Stub health, meant to be wired to real probes.
  - `heartbeat.py.jinja` — daemon thread publishing `HealthState` to Pontus
    (Redpanda) via `AsyncHeartbeatPublisher` every 30s. `confluent_kafka` is
    lazy-imported (optional `kafka` extra); missing extra/broker degrades to
    "no heartbeat," never crashes the server.
  - `observability.py.jinja` — OTLP wiring stub, resolves the Hemera
    collector endpoint from settings; SDK setup itself is a wiring point
    left for the generated repo to fill in.
  - `oneiroi.py.jinja` — no-op memory-emission hook stub (`emit_memory`),
    wiring point for the future Oneiroi memory plane.
  - `{% if mcp %}server.py{% endif %}.jinja` — the FastMCP server: a `ping`
    tool, `TransportSecuritySettings` (DNS-rebinding protection, defaulted
    OFF/allow-all since stars sit behind the Hades gateway), `main()` that
    starts the heartbeat then runs `mcp.run(transport="streamable-http")`.
    Only materializes when `mcp: true` (the whole filename is empty/absent
    when `mcp: false`, copier's conditional-file idiom).
- **`tests/test_smoke.py.jinja`** — version-format check, settings load,
  health surface, observability endpoint, oneiroi no-raise, and (when `mcp`)
  the `ping` tool + server name.
- **`{% if mcp %}Dockerfile{% endif %}.jinja`** — three cases, `{%- if
  core_backed %} ... {%- else %} ... {%- endif %}` inside ONE file:
  1. `core_backed`: multi-stage, schema baked in from
     `mnemosyne-core-base:{core_base_tag}`, builder is stock
     `python:3.12-slim-bookworm` + `uv` binary copied in, needs `git` for the
     `mnemosyne-core` pin.
  2. not `core_backed`: builder is a warm `stellar_core:{kind}-v1.0` base
     image (kind derived from `mcp`/`sovereign_database`/`db_kind` — e.g.
     `python-mcp-pgvector`), no manual `git`/`uv` install needed.
  Both cases produce a non-root runtime stage with a `HEALTHCHECK` dialing
  `$PORT`.
- **`{% if mcp %}compose.yaml{% endif %}.jinja`** — three cases gated by
  `core_backed`/`sovereign_database`: sovereign (own DB, no host port,
  private `{service}-net`), interim-shared (host port + shared corpus
  `DATABASE_URL`), or stateless (no DB block at all). All three join the
  `pantheon` network for the Kafka heartbeat.
- **`.forgejo/workflows/`**:
  - `ci.yml` — PR gate (`on: pull_request`): `uv sync`, pre-commit,
    mypy, pyright, pytest, `pip-audit`, opengrep SAST against
    `rules/sast/`. Runs on the `nas01` self-hosted runner, no docker socket.
  - `admit.yml` — the constellation admission gate: cosign-verify the
    star's image + syft SBOM, cosign-verify + pull the signed
    `ouranos:policy-vN` authority and the `telescope:epoch-N` fleet roster,
    build the admission input via `stellar_core.build_admission_input`, then
    `docker run` the policy eval image — exit code is the verdict
    (fail-closed on error). Needs `/var/run/docker.sock`.
  - `{% if mcp %}deploy.yml{% endif %}.jinja` — build/scan(Trivy)/push/sign
    (cosign)/attest(SBOM to Dependency-Track) on push to `main`. Only
    materializes for MCP stars; no `docker compose up` — the container
    *lifecycle* is Tofu/Nereus-managed, CI only ships the image.
  - `versions.env` — single-sourced tool-version pins (`COSIGN_VERSION`
    etc.) shared by `admit.yml` (verifies) and `deploy.yml` (signs) so they
    can never drift apart.
- **`rules/sast/dataflow.yml`** — vendored opengrep taint rules (SSRF,
  SQLi-shaped), deliberately non-overlapping with ruff's `S` (bandit) rules:
  ruff flags dangerous *sinks*, this flags untrusted *source → sink* flows.
  ASCII-only (opengrep chokes on non-ASCII under the runner's C locale).
- **`cosign.pub`** (unconditional) **and**
  **`{% if core_backed %}cosign.pub{% endif %}`** (conditional, byte-identical
  content) — see Gotchas below; both render to the same destination path
  `cosign.pub` when `core_backed: true`.
- **`{{_copier_conf.answers_file}}.jinja`** → renders to
  `.copier-answers.yml`, copier's own bookkeeping file (records template +
  answers for `copier update`'s 3-way merge).
- Community publish-set: `README.md.jinja`, `CONTRIBUTING.md.jinja`,
  `CHANGELOG.md.jinja`, `LICENSE.jinja` (Apache-2.0), `CODE_OF_CONDUCT.md`,
  `SECURITY.md` (last two are NOT `.jinja` — copied verbatim, no
  placeholders inside).

## Entry points

This repo itself has no CLI/server entry point — it is data (a copier
template), invoked entirely through the `copier` CLI:

- `copier copy <this-repo> <dest>` — scaffold a new repo (see README "Use").
- `copier update` (run *inside* a previously-generated repo) — pull template
  changes via 3-way merge.

Inside a *rendered* repo, the entry points are:
- `mcp: true` → console script `{service_name} = "{package_name}.server:main"`
  (see `pyproject.toml.jinja` `[project.scripts]`), which runs
  `server.main()` — starts the heartbeat thread then `mcp.run()`.
- `mcp: false` → `star.toml`'s `[logic] entrypoint` is
  `"{package_name}:main"` (a console entrypoint the generated library/CLI is
  expected to define — the template does not stub this function itself for
  the non-MCP case).

## Build / Test / Run

The template repo has no build/test of its own. To validate a change to
the template, render it and run the *generated* repo's checks (commands
sourced from `pyproject.toml.jinja` / `template/.forgejo/workflows/ci.yml`
— do not execute without Rob's go-ahead):

```bash
# Render a throwaway instance (defaults + minimal overrides):
copier copy . /tmp/smoke-test --data project_name="Smoke Test" --defaults

# Then, inside the rendered repo:
cd /tmp/smoke-test
uv sync --extra dev
uv run pre-commit run --all-files
uv run mypy src tests
uv run pyright
uv run pytest -q
uv run --with pip-audit pip-audit
```

Re-render with each meaningfully different answer combination before
trusting a template edit — `mcp`, `core_backed`, `sovereign_database`, and
`db_kind` each gate materially different file content (Dockerfile,
compose.yaml, pyproject deps, star.toml entrypoint).

The `_tasks` pipeline in `copier.yml` (what runs on a real `copier copy`,
in order): normalize `.copier-answers.yml`'s trailing newline → `git init`
→ add `origin` (Forgejo) + `github` (mirror) remotes → `uv sync --extra dev`
→ `uv lock` (also runs on `update`, unconditionally) → `detect-secrets scan`
→ `pre-commit install` → `specify init --here --force --integration claude
--script ps --ignore-agent-tools` (spec-kit scaffold) → `specify extension
disable agent-context` → `furnace ignite . --kit code-repo-sdd` → `specify
preset resolve speckit.plan` (verification step). A failure anywhere rolls
back the whole stamp (copier task semantics) — no half-governed repo is
left behind.

## Conventions and gotchas

- **Filenames carry Jinja too, not just contents.** `_subdirectory:
  template` means everything under `template/` is the render root; a path
  segment like `{% if mcp %}server.py{% endif %}` or
  `{{package_name}}` is evaluated per-answer. An empty-string render (the
  `if` false branch) means copier skips that file/dir entirely — this is
  the standard copier conditional-file idiom, not a bug, when you see it
  once. It IS suspicious when you see the same target path produced by two
  different source paths (see next point).
- **Duplicate `cosign.pub`**: `template/cosign.pub` (unconditional) and
  `template/{% if core_backed %}cosign.pub{% endif %}` (same byte content)
  both exist. When `core_backed: true`, both source paths render to the
  same destination `cosign.pub` — copier will process this list in some
  order and one write "wins" harmlessly since the content is identical
  today, but it is redundant and worth collapsing to just the unconditional
  copy if you touch this area (it looks like a leftover from before the
  admission gate applied to every stamped repo, not just `core_backed`
  ones — verify with Rob before deleting, don't assume).
- **`.jinja` suffix controls templating, not just naming.** Files without
  `.jinja` (e.g. `CODE_OF_CONDUCT.md`, `SECURITY.md`, `cosign.pub`,
  `.python-version`) are copied byte-for-byte — no Jinja evaluation inside
  them even if a `{{ }}` string were present. Files *with* `.jinja` have
  the suffix stripped on render AND their content passed through Jinja.
- **The rendered README (`template/README.md.jinja`) legitimately contains
  Jinja placeholders** — per the task framing for this doc, those are
  intentional and must stay unresolved; do not "fix" them.
- **`furnace ignite` and `specify init` are hard dependencies of `_tasks`.**
  They must be on `PATH` (`furnace`) with `$FURNACE_SOURCE` set, and
  `specify` (spec-kit CLI) on `PATH`, for a real `copier copy` to complete.
  Neither is available inside a template-repo-only checkout — this is why
  template validation renders-and-inspects rather than running the full
  live `_tasks` pipeline unless you actually have those tools installed.
- **Governance is deliberately NOT in this repo.** There is no `AGENTS.md`
  or `.claude/` here — by design (see Overview). Don't add one; the
  generated repo gets its governance from `furnace ignite`, poured fresh
  each time from the furnace kit (`code-repo-sdd`), not copied from this
  template.
- **`stellar-core` and `mnemosyne-core`** resolve from a private Forgejo
  PyPI (`forgejo.notusmi.com/api/packages/rob/pypi/simple/`) and a public
  git tag pin respectively — both require network access to Forgejo
  (`--network host` in every workflow) to resolve; there is no vendoring.
- **cosign version pin discipline**: `versions.env`'s `COSIGN_VERSION` is
  read by both `admit.yml` (verify) and `deploy.yml` (sign) — bumping one
  without the other breaks signature verification across the fleet. Change
  it in `versions.env` only, never inline in a workflow.
- **Ruff config is deliberately `select = ["ALL"]` with an explicit ignore
  list** in `pyproject.toml.jinja` — read the ignore-list comments before
  assuming a rule is "obviously" wanted; several ignores (e.g. `FBT`,
  `PLC0415`, `SLF001`) reflect house style decisions, not oversights.

## Related repos

- **`furnace`** — pours the `.claude/` AI-governance layer via `furnace
  ignite . --kit code-repo-sdd`, the final `_task`. Owns
  `furnace/docs/service-repo-standard.md`, the standard this template
  implements. This template repo does not vendor or duplicate furnace's
  kit content — it only invokes the CLI.
- **`constellation`** — owns the `StarManifest` schema that
  `star.toml.jinja` renders against, and `stellar_core.build_admission_input`
  used by `admit.yml`.
- **`stellar_core`** (SDK, PyPI-distributed from Forgejo) — supplies
  `HealthState`, `McpOpsAdapter`/`HttpOpsAdapter`,
  `AsyncHeartbeatPublisher`, and the base Docker images
  (`stellar_core:{kind}-v1.0`) that non-`core_backed` Dockerfiles build FROM.
- **`mnemosyne-core-base`** (image) / **`mnemosyne-core`** (git-pinned
  package) — the `core_backed` path's baked private schema + public core
  package.
- **`ouranos`** — publishes the signed policy authority image
  (`ouranos:policy-vN`) that `admit.yml` evaluates against.
- **`telescope`** — publishes the signed fleet roster
  (`telescope:epoch-N`) that `admit.yml` pulls for cross-star checks.
- Every repo *generated by* this template is itself a candidate
  constellation star, subject to `admit.yml`'s gate on its first PR.

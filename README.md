# service-repo-template

A [copier](https://copier.readthedocs.io) template that stamps a standard,
container-ready Forge MCP service — the formalized vault-mcp shape. Realizes the
service-repo standard (`furnace/docs/service-repo-standard.md`). Pure code; the
AI/governance layer is poured separately by furnace (decoupled by design).

## Use

```bash
copier copy gh:robfischer1/service-repo-template my-new-service
# or from a local checkout:
copier copy /path/to/service-repo-template my-new-service
```

Answer the prompts (project name, package, service name, port). The generated
repo builds, lints, type-checks, and tests green with no manual edits, and
containerizes via its multi-stage non-root Dockerfile.

## Update an existing generated repo

```bash
cd my-new-service
copier update      # 3-way merges template changes, preserving local edits
```

## What you get

- PyPA `src/` layout, PEP 621 `pyproject` (hatchling), `[project.scripts]` console entry
- A minimal FastMCP streamable-HTTP server (stateless, config-via-env)
- Multi-stage non-root Dockerfile + `.dockerignore` + a Compose stack
- Lint/type/test baseline (ruff `select=ALL`, mypy strict, pyright strict, pytest)
- The community publish-set (README, LICENSE, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, CHANGELOG)
- A CI workflow (Python 3.12 / 3.13)
- GitHub triage set: issue forms (bug / feature), a PR template, and Dependabot (weekly `uv` + actions updates)

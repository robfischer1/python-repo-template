# Riso audit (SRSC #1325)

Audited [wyattowalsh/riso](https://github.com/wyattowalsh/riso) (MIT, 0★,
single-maintainer) as a pattern donor for this template — per the SRSC RFC's
"mine Riso for `copier.yml` / `_tasks` / FastMCP-http patterns; pattern-donor
only, not upstream." Audit-then-apply: examine, lift only what is genuinely
better.

## What Riso is

A mix-and-match **monorepo** scaffolder (FastAPI · Fastify · GraphQL · WebSocket ·
MCP · SaaS · multiple docs engines). Heavyweight: a 42 KB `copier.yml`, 32 KB of
Python copier hooks (`pre_gen_project.py` + `post_gen_project.py`), a committed
5.5 MB `actionlint` binary, semantic-release, mise, pnpm. Unproven (0★).

## Patterns examined → disposition

| Pattern | Riso | Ours | Adopt? |
| :-- | :-- | :-- | :-- |
| `copier.yml` | 42 KB, hundreds of options for a configurable monorepo | ~40 lines; one repo = one service | **No** — Riso's configurability is the anti-pattern our standard rejects |
| Init automation | Python pre/post-gen **hooks** (32 KB) | 4-line `_tasks` (git · uv sync · secrets baseline · pre-commit) | **No** — hooks are YAGNI for a single-service init |
| FastMCP server | standalone `fastmcp` (jlowin v2); `server.py` + Pydantic `config.py` + modular `register_*` | official `mcp[cli]` SDK (`mcp.server.fastmcp`), single `server.py` | **No** — we match vault-mcp + the official SDK; split config/registration is a growth refactor, not a template default |
| Toolchain pinning | `.mise.toml` | `.python-version` + uv | **No** — uv is our standard |
| Release automation | semantic-release (`.releaserc.yml`) | git SemVer tags + changelog skill | **Deferred** — a Harden-tier candidate, not a scaffold default |

## Outcome

**Nothing lifted.** Riso's patterns are either anti-patterns for a focused,
single-service standard (configurable monorepo, 32 KB hooks) or deliberate
library/toolchain differences (standalone `fastmcp`, mise). This template — seeded
from the proven vault-mcp — is already the right shape. The audit confirms the
RFC's "pattern-donor only, not upstream" disposition: on inspection, no concrete
pattern warrants import. Riso remains a reference, not a dependency.

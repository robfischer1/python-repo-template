# `{{ service_name }}/infra` — the star's own deploy (scaffolded)

A decentralized star owns its deploy (Smaller Hammers). This directory is the
star's `/infra`: its container declared as tofu against **isolated pg state**
(`schema_name = {{ service_name }}`), applied by the **GitOps deploy plane**
(the tofu-managed `.forgejo/workflows/deploy.yml`): plan-on-PR posted as a
comment, apply-on-merge.

## What's here (scaffolded, ready)

- `main.tf` — the `module "star"` call (image, network from telescope, verb
  prefix, listen port). The module is pinned to a foundry ref.
- `backend.tf` / `providers.tf` / `versions.tf` / `outputs.tf` — the F1 state
  convention + the blessed `output "star"` (read by hephaestus's F3 projection).
- `fleet.json` (gitignored) — materialized per-run by the deploy pipeline from
  the signed telescope contract; never committed.

## Born-ready → live

1. The build pipeline publishes + signs the star's image.
2. Enroll the star in the core: `star_identities` (F4 → `TS_AUTHKEY` repo
   secret), `ci_enrollments` (F5 → this `deploy.yml` is tofu-managed), and a
   `tofu import`/state-mv if it was already running. hephaestus's genesis
   conductor (F9) sequences this.
3. The first infra PR runs plan-on-PR; merge applies against isolated state.
4. `register_star` (F7) re-projects the roster + rolls the gateway route.

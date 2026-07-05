terraform {
  # Per-repo ISOLATED state (Smaller Hammers F1). Isolation key = the pg backend
  # schema_name = this repo's name, supplied at init by the deploy pipeline:
  #   tofu init -backend-config="conn_str=$PG_CONN_STR" \
  #             -backend-config="schema_name={{ service_name }}"
  # Logically isolated, physically co-located in DB `tofu`. State advances only
  # from this repo's own PRs — the merge-if-clean enabler.
  backend "pg" {}
}

# The blessed roster row, re-exposed at the root so hephaestus's F3 projection
# reads it from this repo's state (pg schema = repo). A per-repo row wins the
# overlap with the transitional central aggregation.
output "star" {
  description = "The star's roster row for telescope (the F1->F3 contract)."
  value       = module.star.star
}

variable "docker_host" {
  description = "Docker daemon endpoint. The deploy pipeline exports TF_VAR_docker_host=unix:///var/run/docker.sock on the nas01 runner."
  type        = string
  default     = "unix:///var/run/docker.sock"
}

provider "docker" {
  host = var.docker_host
}

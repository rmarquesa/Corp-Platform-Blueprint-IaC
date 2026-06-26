terraform {
  required_version = ">= 1.3"

  required_providers {
    gitlab = {
      source  = "gitlabhq/gitlab"
      version = "~> 19.1"
    }
  }
}

provider "gitlab" {
  base_url = var.gitlab_base_url
  token    = var.gitlab_token
}

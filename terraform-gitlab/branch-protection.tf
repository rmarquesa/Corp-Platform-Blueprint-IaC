resource "gitlab_branch_protection" "main" {
  for_each = var.enable_branch_protection ? gitlab_project.platform : {}

  project = each.value.id
  branch  = var.default_branch

  push_access_level  = "maintainer"
  merge_access_level = "maintainer"
  allow_force_push   = false
}

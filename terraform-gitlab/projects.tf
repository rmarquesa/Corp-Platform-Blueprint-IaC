resource "gitlab_project" "platform" {
  for_each = var.platform_projects

  name         = each.value.name
  path         = each.key
  namespace_id = gitlab_group.platform.id
  description  = each.value.description

  visibility_level       = "private"
  initialize_with_readme = false

  issues_access_level         = "enabled"
  merge_requests_access_level = "enabled"
  wiki_access_level           = "disabled"
  snippets_access_level       = "disabled"
  packages_enabled            = false
}

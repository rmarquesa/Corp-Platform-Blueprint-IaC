resource "gitlab_project_variable" "protected" {
  for_each = var.protected_ci_variables

  project = gitlab_project.platform[each.value.project_key].id
  key     = each.value.key
  value   = each.value.value

  variable_type = "env_var"
  masked        = each.value.masked
  protected     = each.value.protected
}

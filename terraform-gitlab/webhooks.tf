locals {
  jenkins_hook_projects = var.enable_jenkins_webhooks ? gitlab_project.platform : {}
}

resource "gitlab_project_hook" "jenkins" {
  for_each = local.jenkins_hook_projects

  project = each.value.id
  url     = "${var.jenkins_base_url}/git/notifyCommit?url=http://gitlab.proxmox.local/${var.platform_group_path}/${each.key}.git"

  push_events             = true
  merge_requests_events   = true
  tag_push_events         = false
  enable_ssl_verification = false
  token                   = var.jenkins_webhook_token
}

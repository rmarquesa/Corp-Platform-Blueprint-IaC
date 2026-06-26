output "platform_group_id" {
  description = "GitLab platform group ID."
  value       = gitlab_group.platform.id
}

output "platform_project_ids" {
  description = "GitLab project IDs keyed by project path."
  value       = { for key, project in gitlab_project.platform : key => project.id }
}

output "platform_project_http_urls" {
  description = "GitLab project HTTP clone URLs keyed by project path."
  value       = { for key, project in gitlab_project.platform : key => project.http_url_to_repo }
}

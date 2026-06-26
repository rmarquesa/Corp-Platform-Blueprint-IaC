resource "gitlab_group" "platform" {
  name             = var.platform_group_name
  path             = var.platform_group_path
  description      = "Self-hosted platform bootstrap repositories and automation."
  visibility_level = "private"
}

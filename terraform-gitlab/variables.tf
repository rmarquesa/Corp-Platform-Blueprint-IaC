variable "gitlab_base_url" {
  description = "GitLab API base URL for the self-hosted GitLab instance."
  type        = string
  default     = "http://gitlab.proxmox.local/api/v4/"
}

variable "gitlab_token" {
  description = "Admin/bootstrap token used by the Terraform GitLab provider. Prefer TF_VAR_gitlab_token sourced from Vault."
  type        = string
  sensitive   = true
}

variable "platform_group_path" {
  description = "Top-level GitLab group/path for platform repositories."
  type        = string
  default     = "platform"
}

variable "platform_group_name" {
  description = "Display name for the platform GitLab group."
  type        = string
  default     = "Platform"
}

variable "default_branch" {
  description = "Default branch protected by the platform policy. The branch must exist before branch protection can be applied."
  type        = string
  default     = "main"
}

variable "platform_projects" {
  description = "GitLab projects managed under the platform group. Map key becomes the project path."
  type = map(object({
    name        = string
    description = string
  }))

  default = {
    proxmox = {
      name        = "proxmox"
      description = "Proxmox platform infrastructure-as-code, Ansible bootstrap, Helm charts and GitOps manifests."
    }
    jenkins-jobs = {
      name        = "jenkins-jobs"
      description = "Jenkins Job DSL and shared CI/CD job definitions for the platform."
    }
    docker-images = {
      name        = "docker-images"
      description = "Container image build definitions for platform services published to Harbor."
    }
  }
}

variable "enable_branch_protection" {
  description = "Whether Terraform should create branch protection resources. Disable until default branches exist in empty projects."
  type        = bool
  default     = false
}

variable "enable_jenkins_webhooks" {
  description = "Whether Terraform should configure GitLab project hooks pointing to Jenkins."
  type        = bool
  default     = false
}

variable "jenkins_base_url" {
  description = "Internal Jenkins base URL used for GitLab webhooks."
  type        = string
  default     = "http://jenkins.proxmox.local"
}

variable "jenkins_webhook_token" {
  description = "Optional secret token sent by GitLab project hooks to Jenkins or a webhook bridge."
  type        = string
  sensitive   = true
  default     = null
}

variable "protected_ci_variables" {
  description = "Optional protected GitLab CI/CD variables. Values should be supplied through tfvars or TF_VAR_* from Vault, never committed. Do not use secret values as map keys."
  type = map(object({
    project_key = string
    key         = string
    value       = string
    masked      = optional(bool, true)
    protected   = optional(bool, true)
  }))
  default = {}
}

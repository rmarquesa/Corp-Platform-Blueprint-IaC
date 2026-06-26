# Terraform GitLab Stack

This stack manages GitLab objects after the GitLab VM and service are bootstrapped by the root Proxmox Terraform stack and Ansible.

It intentionally does **not** install GitLab. Installation belongs to:

```text
root Terraform -> creates VM
Ansible 09-gitlab -> installs/configures GitLab CE
terraform-gitlab -> creates groups/projects/policies through GitLab API
```

## Provider

Official GitLab Terraform provider:

```hcl
gitlab = {
  source  = "gitlabhq/gitlab"
  version = "~> 19.1"
}
```

For the self-hosted instance:

```hcl
provider "gitlab" {
  base_url = "http://gitlab.proxmox.local/api/v4/"
  token    = var.gitlab_token
}
```

## Bootstrap Token

Initial practical flow:

1. Create an admin/bootstrap token in GitLab after first boot.
2. Store it in Vault:

```bash
vault kv put kv/gitlab/terraform token=<token>
```

3. Export it before running Terraform:

```bash
export TF_VAR_gitlab_token="$(vault kv get -field=token kv/gitlab/terraform)"
```

A future Ansible task may create this token automatically and write it to Vault.

## Validate

```bash
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
```

## Apply

Only apply after GitLab is reachable and the token is available:

```bash
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

## First Managed Objects

- Group: `platform`
- Projects:
  - `platform/proxmox`
  - `platform/jenkins-jobs`
  - `platform/docker-images`

Branch protection and Jenkins webhooks are disabled by default because empty repositories may not have their default branch yet and webhook strategy may evolve.

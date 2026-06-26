# Platform Operating Model

This repository is a company-grade bootstrap blueprint for a self-hosted platform on Proxmox. It intentionally keeps **GitLab**, **Jenkins**, and **Harbor** as separate systems because the goal is not a minimal homelab; the goal is to demonstrate enterprise infrastructure patterns and automation discipline.

## North Star

Provision a repeatable internal platform where infrastructure, configuration, source control, CI/CD, container registry, Kubernetes applications, and secrets are all managed as code as far as practical.

```text
Terraform          -> Proxmox infrastructure objects
Ansible            -> host and external-service configuration
Terraform GitLab   -> GitLab groups/projects/policies after GitLab exists
GitLab             -> source control and platform project metadata
Jenkins            -> enterprise CI/CD orchestration and validation
Harbor             -> dedicated enterprise container registry
ArgoCD + Helm      -> Kubernetes desired state and GitOps reconciliation
Vault + ESO        -> secrets lifecycle and Kubernetes secret materialisation
```

## Control Plane Flow

```text
Developer / Platform Engineer
  -> pushes code to GitLab
  -> Jenkins runs validation/build pipelines
  -> Jenkins pushes runtime images to Harbor
  -> GitOps changes update Helm values/manifests
  -> ArgoCD reconciles desired state into k3s
  -> k3s pulls images from Harbor
```

## Ownership Boundaries

| Layer | Owner | Purpose | Should not own |
|---|---|---|---|
| Proxmox infra | Terraform root stack | VMs, LXCs, disks, network, IPs, cloud-init | Package installation or app config |
| Host/service config | Ansible | OS packages, Docker/Compose services, k3s bootstrap, DNS, Vault, Harbor, GitLab | Long-lived Kubernetes desired state |
| GitLab objects | Terraform GitLab stack | Groups, projects, branch protection, variables, webhooks | Installing GitLab itself |
| Kubernetes apps | Helm + ArgoCD | Platform apps, app-of-apps, sync waves, drift correction | Host-level bootstrap |
| CI/CD | Jenkins | Validation, plans, image builds, promotion workflows | Ungated destructive apply by default |
| Registry | Harbor | Runtime image storage, scanning, robot accounts, retention | Source control |
| Secrets | Vault + External Secrets | Secret storage and delivery to Kubernetes | Plaintext secrets in Git |

## Why Keep GitLab, Jenkins and Harbor?

### GitLab

GitLab is the internal Git and project API layer. It stores repositories, groups, branches, merge policies, variables and webhooks. The GitLab Terraform provider manages this configuration after the GitLab VM is bootstrapped.

### Jenkins

Jenkins demonstrates enterprise CI/CD skills that are still common in corporate environments: JCasC, Job DSL, controller hardening, Kubernetes agents, credentials binding, and explicit pipeline orchestration. It should validate and build; destructive applies should require deliberate gates.

### Harbor

Harbor remains the dedicated artifact registry. This demonstrates separation of code and runtime artifacts, robot accounts, image scanning, retention and a registry lifecycle independent from the Git server.

## Bootstrap Sequence Summary

1. Prepare secrets locally/Vault.
2. Run Terraform Proxmox stack to create VMs/LXCs/network.
3. Run Ansible base VM preparation.
4. Bootstrap k3s, PostgreSQL/Patroni, CoreDNS, Vault, Harbor and GitLab.
5. Bootstrap Traefik, Longhorn and ArgoCD as the recovery layer.
6. Let ArgoCD reconcile the Kubernetes platform apps.
7. Deploy Jenkins via Helm/JCasC.
8. Run Terraform GitLab stack to create GitLab groups/projects/policies/webhooks.
9. Validate end-to-end flow: GitLab -> Jenkins -> Harbor -> ArgoCD -> k3s.

## Promotion Model

Default mode should be conservative:

- Jenkins may run validation and build automatically.
- Jenkins may push images to Harbor automatically for trusted branches.
- Jenkins should not run destructive `terraform apply`, Ansible service mutations, or production-like deploy changes without an explicit gate.
- ArgoCD reconciles only committed desired state.

## First End-to-End Demonstration

Use PgBouncer as the first complete artifact path:

```text
platform/proxmox repository
  -> docker/pgbouncer/Jenkinsfile
  -> Jenkins docker/pgbouncer-build
  -> harbor.proxmox.local/platform/pgbouncer:<tag>
  -> helm/pgbouncer/values.yaml
  -> argocd/apps/pgbouncer.yaml
  -> k3s deployment pulls image from Harbor
```

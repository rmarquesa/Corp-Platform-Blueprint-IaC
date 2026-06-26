# platform-blueprint

Production-grade corporate infrastructure blueprint for a single Proxmox node. The platform is provisioned with **Terraform**, configured with **Ansible**, operated through **ArgoCD GitOps**, and extended with **GitLab**, **Jenkins**, and **Harbor** to demonstrate enterprise source-control, CI/CD, and artifact-management patterns.

> Goal: not a toy environment. The design models real platform decisions: HA control plane, HA database, distributed storage, private access, centralized identity, observability, and no direct public port forwarding.

---

## Architecture

```text
                        Internet
                           │
                    Cloudflare DNS
                           │
                   Cloudflare Tunnel              Tailscale VPN
                   (cloudflared pod)              (LXC subnet router)
                           │                           │
                    ┌──────▼───────────────────────────▼──────┐
                    │      Traefik (Gateway API v1)            │
                    │      ClusterIP / LoadBalancer on k3s      │
                    └──┬──────────┬────────────┬───────────────┘
                       │          │            │
                    ArgoCD     Keycloak     Grafana / Longhorn UI
                       │
           ┌───────────▼──────────────────────────────┐
           │             k3s HA Cluster                │
           │                                           │
           │  Masters ×3        control-plane only     │
           │  kube-vip VIP      10.10.0.100            │
           │                                           │
           │  Infra Workers ×3  workload=infra:NoSched │
           │                    Longhorn, ArgoCD,       │
           │                    monitoring, ingress,    │
           │                    Jenkins agents          │
           │                                           │
           │  App Workers ×2    workload=app            │
           │                    User workloads          │
           └───────────────────────────────────────────┘
                           │
           ┌───────────────▼───────────────────────────┐
           │          External / LXC Services           │
           │                                           │
           │  CoreDNS       internal DNS               │
           │  PostgreSQL HA Patroni + etcd             │
           │  GitLab        source control / API        │
           │  Jenkins       CI/CD control plane         │
           │  Harbor        dedicated image registry    │
           │  Vault         secrets management          │
           │  Tailscale     subnet router only          │
           └───────────────────────────────────────────┘

      Source -> CI/CD -> Artifact -> GitOps runtime path:

      GitLab repositories -> Jenkins pipelines -> Harbor images
                -> Helm values / GitOps commits -> ArgoCD -> k3s
```

---

## Design Principles

- **No single points of failure where practical** — k3s has 3 masters behind kube-vip. PostgreSQL runs as Patroni/etcd across 3 DB VMs. Longhorn replicates volumes across infra workers.
- **Workload segregation** — platform tooling runs on tainted infra workers; application workloads run on app workers.
- **GitOps-first after bootstrap** — Traefik, Longhorn, and ArgoCD are bootstrapped manually as the recovery layer; the rest of the Kubernetes stack is reconciled by ArgoCD.
- **Zero open router ports** — public access uses Cloudflare Tunnel; private access uses a dedicated Tailscale LXC advertising `10.10.0.0/24`.
- **No Tailscale in Kubernetes** — Tailscale is intentionally **not** installed through ArgoCD and there is no Tailscale Kubernetes Operator in this design.
- **Identity-first** — Keycloak provides OIDC/SSO for internal services.
- **Enterprise separation of concerns** — GitLab owns source control/project metadata, Jenkins owns CI/CD orchestration, Harbor owns runtime artifacts, and ArgoCD owns Kubernetes desired state.

---

## Stack

### Provisioning & Configuration

| Tool | Purpose |
|---|---|
| Proxmox VE 8.x | Hypervisor for VMs/LXCs |
| Terraform + bpg/proxmox | VM/LXC/SDN lifecycle |
| Ansible | OS-level configuration and service bootstrap |
| Terraform + gitlabhq/gitlab | GitLab groups/projects/policies after GitLab exists |
| Helm | Kubernetes package rendering/install |
| ArgoCD | GitOps reconciliation after bootstrap |

### Kubernetes Platform

| Component | Version | Purpose |
|---|---:|---|
| k3s | v1.35.4+k3s1 | Kubernetes distribution |
| kube-vip | latest | API VIP + LoadBalancer pool |
| Traefik | 39.0.9 | Ingress controller / Gateway API v1 |
| Longhorn | 1.7.2 | Distributed block storage |
| ArgoCD | 9.5.11 | GitOps continuous delivery |

### Developer Platform & CI/CD

| Component | Version | Purpose |
|---|---:|---|
| GitLab CE | 17.11.1-ce.0 | Internal Git server, project API and repository source of truth |
| Jenkins | 2.555.1 | Enterprise CI/CD via JCasC, Job DSL and Kubernetes agents |
| Harbor | 2.12.2 | Dedicated container registry, robot accounts and image scanning |

### Observability

| Component | Version | Purpose |
|---|---:|---|
| kube-prometheus-stack | 70.4.2 | Prometheus, Grafana, Alertmanager |
| Loki | 6.29.0 | Log aggregation |
| Tempo | 1.14.1 | Distributed tracing |

### Identity, Data & Access

| Component | Version | Purpose |
|---|---:|---|
| Keycloak | 7.1.11 chart | SSO / OIDC identity provider |
| PostgreSQL | 17 | HA database via Patroni + etcd |
| PgBouncer | 1.1.0 chart | Connection pooling |
| Redis HA | 21.2.7 chart | Cache with Sentinel |
| Harbor | 2.12.2 | Dedicated private container registry |
| Vault | — | Secrets management |
| CoreDNS | 1.12.1 | Internal DNS for `proxmox.local` |
| cloudflared | 2025.4.0 | Cloudflare Tunnel |
| Tailscale | — | LXC subnet router only |

---

## Infrastructure Layout

### Virtual Machines

| Name | ID | IP | Spec | Role |
|---|---:|---|---|---|
| k8s-master-1 | 201 | 10.10.0.10 | 2 vCPU / 4 GB | k3s control-plane |
| k8s-master-2 | 202 | 10.10.0.11 | 2 vCPU / 4 GB | k3s control-plane |
| k8s-master-3 | 203 | 10.10.0.12 | 2 vCPU / 4 GB | k3s control-plane |
| k8s-infra-1 | 204 | 10.10.0.13 | 4 vCPU / 8 GB | infra worker |
| k8s-infra-2 | 205 | 10.10.0.14 | 4 vCPU / 8 GB | infra worker |
| k8s-infra-3 | 206 | 10.10.0.15 | 4 vCPU / 8 GB | infra worker |
| k8s-app-1 | 207 | 10.10.0.16 | 2 vCPU / 4 GB | app worker |
| k8s-app-2 | 208 | 10.10.0.17 | 2 vCPU / 4 GB | app worker |
| db-1 | 210 | 10.10.0.20 | 2 vCPU / 4 GB | PostgreSQL / Patroni |
| db-2 | 211 | 10.10.0.22 | 2 vCPU / 4 GB | PostgreSQL / Patroni |
| db-3 | 213 | 10.10.0.24 | 2 vCPU / 4 GB | PostgreSQL / Patroni no-failover/no-sync |
| harbor | 220 | 10.10.0.30 | 4 vCPU / 8 GB | dedicated container registry |
| gitlab | 222 | 10.10.0.32 | 4 vCPU / 8 GB | GitLab CE source control |

### LXC Containers

| Name | ID | IP | Role |
|---|---:|---|---|
| dns | 200 | 10.10.0.5 | CoreDNS internal resolver |
| vault | 221 | 10.10.0.31 | Vault secrets management |
| tailscale | 230 | 10.10.0.40 | Tailscale subnet router for `10.10.0.0/24` |

### Virtual IPs

| VIP | Purpose |
|---|---|
| 10.10.0.21 | PostgreSQL primary via Patroni + vip-manager |
| 10.10.0.100 | k3s API server via kube-vip |
| 10.10.0.200–250 | kube-vip LoadBalancer pool |

---

## Repository Structure

```text
.
├── *.tf                         # Terraform root stack for Proxmox resources
├── terraform-gitlab/            # Terraform stack for GitLab groups/projects/policies
├── modules/
│   ├── vm/                      # VM module
│   └── lxc/                     # LXC module
├── ansible/
│   ├── 01-prepare_vms/          # QEMU guest agent prep through Proxmox host
│   ├── 02-k3s/                  # k3s HA bootstrap, kube-vip, labels/taints
│   ├── 03-postgres/             # PostgreSQL 17 + Patroni + etcd + vip-manager
│   ├── 04-harbor/               # Docker + Harbor installer
│   ├── 05-dns/                  # CoreDNS internal DNS
│   ├── 06-tailscale/            # Tailscale LXC subnet router
│   ├── 07-vault/                # Vault + Raft storage
│   ├── 08-vault-k3s/            # Vault Kubernetes auth and platform policies
│   └── 09-gitlab/               # GitLab CE via Docker Compose
├── helm/                        # Local wrapper charts and values
├── argocd/apps/                 # App-of-Apps manifests with sync waves
├── docker/                      # Platform image build contexts and Jenkinsfiles
├── docs/
│   ├── platform-operating-model.md
│   ├── runbooks/bootstrap.md
│   └── tailscale-acl.hujson     # Tailscale ACL for LXC-only subnet router
└── scripts/
    ├── shutdown.sh              # Graceful Proxmox guest shutdown order
    └── validate.sh              # Local validation suite
```

---

## Prerequisites

- Proxmox VE 8.x node.
- Terraform >= 1.3.
- Ansible >= 2.15.
- Helm and kubectl.
- SSH key pair for VM/LXC access.
- Domain managed by Cloudflare.
- Tailscale account.

---

## Getting Started

### 1. Credentials

```bash
cp secrets.sh.example secrets.sh
# Fill in all tokens/passwords, then:
source secrets.sh
```

`secrets.sh`, `terraform.tfvars`, and Terraform state files are intentionally ignored by Git.

### 2. Provision infrastructure

```bash
terraform init
terraform apply -parallelism=2
```

This creates the Proxmox SDN network, downloads templates, and provisions all VMs/LXCs.

### 3. Prepare VMs

```bash
cd ansible
ansible-playbook 01-prepare_vms/playbook.yml -i 01-prepare_vms/inventory/hosts.yml
```

### 4. Bootstrap k3s

```bash
ansible-playbook 02-k3s/site.yml -i 02-k3s/inventory/hosts.yml
```

This bootstraps the first server, joins the other servers/workers, deploys kube-vip, and applies labels/taints.

### 5. Configure PostgreSQL HA

```bash
ansible-playbook 03-postgres/playbook.yml -i 03-postgres/inventory/hosts.yml
```

Installs etcd on all DB nodes, installs PostgreSQL 17, configures Patroni, and manages the `10.10.0.21` floating VIP.

### 6. Configure CoreDNS

```bash
ansible-playbook 05-dns/playbook.yml -i 05-dns/inventory/hosts.yml
```

CoreDNS serves `proxmox.local` names and points platform service hostnames at the Traefik/kube-vip frontend.

### 7. Configure Harbor

```bash
ansible-playbook 04-harbor/playbook.yml -i 04-harbor/inventory/hosts.yml
```

### 8. Configure Vault

```bash
ansible-playbook 07-vault/site.yml -i 07-vault/inventory/hosts.yml
# Retrieve /root/vault-init.json from the Vault LXC and store unseal keys securely.
```

### 9. Configure GitLab

GitLab is the internal source-control and project API layer. Harbor remains the dedicated image registry.

```bash
export VAULT_GITLAB_ROOT_PASSWORD="$(vault kv get -field=root_password kv/gitlab/admin)"
ansible-playbook 09-gitlab/site.yml -i 09-gitlab/inventory/inventory.yml
```

### 10. Configure Tailscale LXC subnet router

Tailscale is deployed only in the LXC at `10.10.0.40`. Do not add a Tailscale Operator or ArgoCD app unless the architecture intentionally changes.

1. Apply `docs/tailscale-acl.hujson` in the Tailscale ACL editor.
2. Generate a tagged pre-auth key for `tag:subnet-router`.
3. Export it as `VAULT_TAILSCALE_AUTH_KEY`.
4. Run:

```bash
ansible-playbook 06-tailscale/site.yml -i 06-tailscale/inventory/hosts.yml
```

The ACL auto-approves route `10.10.0.0/24` for `tag:subnet-router`; otherwise approve the subnet route manually in the Tailscale admin console.

### 11. Platform bootstrap: manual recovery layer

Traefik, Longhorn, and ArgoCD are installed manually. They are the recovery layer: if ArgoCD breaks, Traefik/ArgoCD access remains independently recoverable.

```bash
# Gateway API CRDs
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.1/standard-install.yaml

# Traefik
helm repo add traefik https://traefik.github.io/charts && helm repo update
helm dependency build helm/traefik/
helm upgrade --install traefik helm/traefik/ \
  --namespace traefik --create-namespace \
  -f helm/traefik/values.yaml \
  --wait --timeout 3m

# Longhorn
helm repo add longhorn https://charts.longhorn.io && helm repo update
helm dependency build helm/longhorn/
helm upgrade --install longhorn helm/longhorn/ \
  --namespace longhorn-system --create-namespace \
  -f helm/longhorn/values.yaml \
  --wait --timeout 5m

# ArgoCD
ARGO_PWD="<password>"
ARGO_HASH=$(htpasswd -nbBC 10 "" "$ARGO_PWD" | tr -d ':\n' | sed 's/$2y/$2a/')
helm repo add argo https://argoproj.github.io/argo-helm && helm repo update
helm dependency build helm/argocd/
helm upgrade --install argocd helm/argocd/ \
  --namespace argocd --create-namespace \
  -f helm/argocd/values.yaml \
  --set argo-cd.configs.secret.argocdServerAdminPassword="$ARGO_HASH" \
  --wait --timeout 5m
```

### 12. GitOps takes over

```bash
kubectl apply -f argocd/apps/root.yaml
```

ArgoCD syncs the remaining stack:

| Wave | Apps |
|---:|---|
| 1 | kube-prometheus-stack, Loki, Tempo |
| 2 | Keycloak, PgBouncer, Redis |
| 3 | cloudflared |

Longhorn is installed in the manual bootstrap step and is not currently part of `argocd/apps`.

### 13. Configure GitLab objects

After GitLab is reachable and a bootstrap token is available, use the dedicated Terraform GitLab stack:

```bash
export TF_VAR_gitlab_token="$(vault kv get -field=token kv/gitlab/terraform)"
cd terraform-gitlab
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

This creates and maintains GitLab groups, projects, branch protection, CI/CD variables and Jenkins webhooks as code.

---

## Validation

Run the local validation suite before committing or applying changes:

```bash
scripts/validate.sh
```

It checks Terraform formatting/validation for the Proxmox and GitLab stacks, Helm chart linting, Ansible syntax, YAML parsing for non-template files, and optional secret scanning with gitleaks when available.

For live bootstrap testing against the Proxmox host, use the safe preflight wrapper:

```bash
scripts/bootstrap-preflight.sh --plan --plan-file tfplan.bootstrap-test
```

The detailed rebuild procedure is documented in `docs/runbooks/bootstrap-test-plan.md`.

---

## Node Scheduling

| Pool | Taint | Runs |
|---|---|---|
| Masters | `node-role.kubernetes.io/control-plane:NoSchedule` | k3s control plane only |
| Infra workers | `workload=infra:NoSchedule` | platform tooling |
| App workers | — | user workloads |

DaemonSets such as node-exporter, Longhorn manager, and Promtail use `operator: Exists` tolerations where they must run on all nodes.

---

## Secrets

All credentials are injected at runtime via environment variables or Kubernetes Secrets. Do not commit real credentials.

Intended steady-state flow:

```text
Vault ──► External Secrets Operator ──► Kubernetes Secrets
```

Until that flow is complete, bootstrap-only secrets may be created manually or sourced from `secrets.sh` locally.

---

## Maintenance

- **Upgrade a Helm chart** — edit dependency `version` in `helm/<chart>/Chart.yaml`, run `helm dependency update helm/<chart>/`, validate, commit, and let ArgoCD sync.
- **Upgrade k3s** — update `ansible/02-k3s/manifests/upgrade-plans.yaml` and apply the plan through the system-upgrade-controller flow.
- **Add an application** — create `helm/<app>/`, add an `argocd/apps/<app>.yaml`, validate, then push.
- **Scale workers** — edit `k8s-workers-app.tf` or `k8s-workers-infra.tf`, run `terraform apply`, then re-run the k3s playbook.
- **Tailscale changes** — update only the LXC Ansible role and `docs/tailscale-acl.hujson`; do not add Tailscale to ArgoCD in the current architecture.
- **GitLab project changes** — update `terraform-gitlab/`, run `terraform plan`, and apply only after GitLab is reachable and the reviewed plan is accepted.
- **CI/CD changes** — update Jenkins JCasC/Job DSL in `helm/jenkins/`, validate with `tests/validate_jenkins_chart.py`, and let Helm/ArgoCD reconcile.

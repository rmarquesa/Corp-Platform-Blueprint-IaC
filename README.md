# platform-blueprint

A production-grade corporate infrastructure blueprint running on a single Proxmox node. Built to simulate the full platform stack a company needs to operate with resilience, security, and observability — provisioned with **Terraform**, configured with **Ansible**, and fully GitOps-managed via **ArgoCD**.

> The goal is not a toy environment. Every component reflects real engineering decisions: HA databases, distributed storage, centralized identity, full observability, and zero open ports to the internet.

---

## Architecture

```
                        Internet
                           │
                    Cloudflare DNS
                           │
                   Cloudflare Tunnel        Tailscale VPN
                   (cloudflared pod)     (LXC — private access)
                           │                    │
                    ┌──────▼────────────────────▼──────┐
                    │     Traefik (Gateway API v1)      │
                    │     ClusterIP — infra workers     │
                    └──┬───────┬──────────┬─────────────┘
                       │       │          │
                   ArgoCD  Keycloak   Grafana / Longhorn UI
                       │
           ┌───────────▼──────────────────────────────┐
           │           k3s HA Cluster                  │
           │                                           │
           │  Masters ×3        control-plane only     │
           │  kube-vip VIP      10.10.0.100            │
           │                                           │
           │  Infra Workers ×3  workload=infra:NoSched │
           │                    Longhorn, ArgoCD,       │
           │                    monitoring, ingress     │
           │                                           │
           │  App Workers ×2    workload=app            │
           │                    User workloads          │
           └───────────────────────────────────────────┘
                           │
           ┌───────────────▼───────────────────────────┐
           │        External Services                   │
           │                                           │
           │  PostgreSQL HA  Patroni + etcd            │
           │  primary · replica · etcd arbiter         │
           │  floating VIP via vip-manager             │
           │                                           │
           │  Harbor    Container registry             │
           │  Vault     Secrets management             │
           └───────────────────────────────────────────┘
```

---

## Design Principles

**No single points of failure** — k3s control-plane runs on 3 masters with kube-vip providing a stable API VIP. PostgreSQL uses Patroni with etcd for automatic failover. Longhorn replicates volumes across infra workers.

**Workload segregation** — infra tooling (Traefik, ArgoCD, monitoring, Longhorn) runs exclusively on infra workers via taints and node selectors. Application workloads run on separate app workers with no scheduling conflict.

**GitOps-first** — no `kubectl apply` in production after bootstrap. All application state lives in Git. ArgoCD reconciles continuously with sync waves to enforce dependency ordering.

**Zero open ports** — all public traffic enters via Cloudflare Tunnel (no firewall rules, no exposed IPs). Private access uses Tailscale subnet routing.

**Identity-first** — Keycloak provides SSO across all internal services. Grafana, ArgoCD, and Longhorn authenticate via OIDC. No local user databases per service.

---

## Stack

### Provisioning & Configuration
| Tool | Purpose |
|---|---|
| Proxmox VE 8.x | Hypervisor — VMs and LXC containers |
| Terraform + bpg/proxmox ~> 0.70 | Infrastructure as Code — VM/LXC lifecycle, SDN, cloud-init |
| Ansible | OS-level configuration, cluster bootstrap, service installation |

### Kubernetes Platform
| Component | Version | Purpose |
|---|---|---|
| k3s | v1.35.4+k3s1 | Kubernetes distribution |
| kube-vip | latest | Control-plane HA VIP + LoadBalancer |
| Traefik | 39.0.9 | Ingress controller, Gateway API v1 |
| Longhorn | 1.7.2 | Distributed block storage with replication |
| ArgoCD | 9.5.11 | GitOps continuous delivery |

### Observability
| Component | Version | Purpose |
|---|---|---|
| kube-prometheus-stack | 70.4.2 | Metrics — Prometheus + Grafana + Alertmanager |
| Loki | 6.29.0 | Log aggregation |
| Tempo | 1.14.1 | Distributed tracing |

Grafana is pre-configured with 11 dashboards across 7 folders (Kubernetes, GitOps, Ingress, Storage, Database, Identity, Observability) and full Loki↔Tempo correlation.

### Identity & Security
| Component | Version | Purpose |
|---|---|---|
| Keycloak | bitnami 24.4.13 | SSO / OIDC identity provider |
| HashiCorp Vault | latest | Secrets management (Raft storage) |

### Data Layer
| Component | Version | Purpose |
|---|---|---|
| PostgreSQL 17 | — | Primary database (HA via Patroni + etcd) |
| PgBouncer | 1.2.7 | Connection pooler |
| Redis HA | bitnami 21.2.7 | Cache with Sentinel |

### Networking & Access
| Component | Version | Purpose |
|---|---|---|
| cloudflared | 2025.4.0 | Cloudflare Tunnel — zero-trust public access |
| Tailscale | — | VPN subnet router — private access |

### Registry
| Component | Purpose |
|---|---|
| Harbor | Private container registry with RBAC and vulnerability scanning |

---

## Infrastructure Layout

### Virtual Machines
| Name | ID | IP | Spec | Role |
|---|---|---|---|---|
| k8s-master-1/2/3 | 201–203 | 10.10.0.10–12 | 2vCPU / 4 GB | k3s control-plane |
| k8s-infra-1/2/3 | 204–206 | 10.10.0.13–15 | 4vCPU / 8 GB | Infra workers |
| k8s-app-1/2 | 207–208 | 10.10.0.16–17 | 2vCPU / 4 GB | App workers |
| db-1 | 210 | 10.10.0.20 | 2vCPU / 4 GB | PostgreSQL primary |
| db-2 | 211 | 10.10.0.22 | 2vCPU / 4 GB | PostgreSQL replica |
| db-arbiter | 212 | 10.10.0.23 | 1vCPU / 512 MB | etcd arbiter |
| harbor | 220 | 10.10.0.30 | 4vCPU / 8 GB | Container registry |

### LXC Containers
| Name | ID | IP | Role |
|---|---|---|---|
| vault | 221 | 10.10.0.31 | Secrets management |
| tailscale | 230 | 10.10.0.40 | VPN subnet router |

### Virtual IPs
| VIP | Purpose |
|---|---|
| 10.10.0.21 | PostgreSQL primary (Patroni + vip-manager) |
| 10.10.0.100 | k3s API server (kube-vip) |
| 10.10.0.200–250 | LoadBalancer pool (kube-vip cloud controller) |

---

## Network

All nodes run on a Proxmox SDN isolated network (`10.10.0.0/24`). SNAT provides outbound internet access via the host.

**Public traffic** — Cloudflare Tunnel connects the `cloudflared` pod to Cloudflare's edge. TLS terminates at Cloudflare. No ports are forwarded on the router.

**Private traffic** — The Tailscale LXC advertises `10.10.0.0/24` as a subnet route. Any device on the Tailscale network reaches all internal services directly.

---

## Repository Structure

```
.
├── main.tf                     # Provider + backend configuration
├── variables.tf                # Input variables
├── secrets.sh.example          # Environment variables template
├── network.tf                  # SDN zone, vnet, SNAT
├── template.tf                 # Ubuntu 24.04 cloud image + vendor-data
├── k8s-masters.tf              # k3s master VMs
├── k8s-workers-infra.tf        # Infra worker VMs
├── k8s-workers-app.tf          # App worker VMs
├── database.tf                 # PostgreSQL HA VMs
├── registry.tf                 # Harbor VM
├── vault.tf                    # Vault LXC
├── vpn.tf                      # Tailscale LXC
│
├── modules/
│   ├── vm/                     # VM module — cloud-init, disk, network
│   └── lxc/                    # LXC module — nesting, TUN device
│
├── ansible/
│   ├── 01-prepare_vms/         # Pre-flight: QEMU agent via Proxmox host
│   ├── 02-k3s/                 # k3s HA bootstrap, kube-vip, node labels
│   ├── 03-postgres/            # Patroni + etcd + vip-manager
│   ├── harbor/                 # Docker + Harbor installer
│   ├── vault/                  # Vault + Raft storage
│   └── tailscale/              # Tailscale subnet router
│
├── helm/
│   ├── traefik/                # Traefik v3 + Gateway API
│   ├── longhorn/               # Distributed storage
│   ├── argocd/                 # ArgoCD HA
│   ├── kube-prometheus-stack/  # Prometheus + Grafana + Alertmanager
│   ├── loki/                   # Log aggregation
│   ├── tempo/                  # Distributed tracing
│   ├── keycloak/               # Identity provider
│   ├── pgbouncer/              # Connection pooler
│   ├── redis/                  # Redis HA
│   └── cloudflared/            # Cloudflare Tunnel
│
└── argocd/
    └── apps/                   # App-of-Apps manifests with sync waves
```

---

## Prerequisites

- Proxmox VE 8.x node
- Terraform ≥ 1.3 and Ansible ≥ 2.15 installed locally
- An SSH key pair for VM access
- A domain managed by Cloudflare
- A Tailscale account

---

## Getting Started

### 1. Credentials

```bash
cp secrets.sh.example secrets.sh
# Fill in all tokens and passwords
source secrets.sh
```

### 2. Provision infrastructure

```bash
terraform init
terraform apply -parallelism=2
```

Creates the SDN network, downloads the Ubuntu 24.04 cloud image, and provisions all VMs and LXC containers.

### 3. Pre-flight VM preparation

Enables the QEMU guest agent on every VM via the Proxmox host. Idempotent.

```bash
cd ansible
ansible-playbook 01-prepare_vms/playbook.yml -i 01-prepare_vms/inventory/hosts.yml
```

### 4. k3s cluster

```bash
ansible-playbook 02-k3s/site.yml
```

Bootstraps the first master, joins remaining masters via kube-vip VIP (`10.10.0.100`), deploys kube-vip manifests, joins all workers, and applies node labels and taints.

### 5. PostgreSQL HA

```bash
ansible-playbook 03-postgres/playbook.yml -i 03-postgres/inventory/hosts.yml
```

Installs etcd on all three DB nodes, installs PostgreSQL 17, configures Patroni, and sets up vip-manager for the floating VIP at `10.10.0.21`.

### 6. Harbor

```bash
ansible-playbook harbor/playbook.yml -i harbor/inventory/hosts.yml
```

### 7. Vault

```bash
ansible-playbook vault/playbook.yml -i vault/inventory/hosts.yml
# Retrieve /root/vault-init.json from the Vault LXC and store the unseal keys securely
```

### 8. Tailscale

```bash
ansible-playbook tailscale/site.yml -i tailscale/inventory/hosts.yml
# Approve the subnet route 10.10.0.0/24 in the Tailscale admin console
```

### 9. Platform bootstrap (manual, run once)

Traefik and ArgoCD are installed manually — they are the recovery layer. If ArgoCD breaks, Traefik is still serving and you can access the ArgoCD UI to fix it.

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
ARGO_HASH=$(htpasswd -nbBC 10 "" $ARGO_PWD | tr -d ':\n' | sed 's/$2y/$2a/')
helm repo add argo https://argoproj.github.io/argo-helm && helm repo update
helm dependency build helm/argocd/
helm upgrade --install argocd helm/argocd/ \
  --namespace argocd --create-namespace \
  -f helm/argocd/values.yaml \
  --set argo-cd.configs.secret.argocdServerAdminPassword="$ARGO_HASH" \
  --wait --timeout 5m
```

### 10. GitOps takes over

```bash
kubectl apply -f argocd/apps/root.yaml
```

ArgoCD syncs the remaining stack in waves:

| Wave | Apps |
|---|---|
| 0 | Longhorn |
| 1 | kube-prometheus-stack, Loki, Tempo |
| 2 | Keycloak, PgBouncer, Redis |
| 3 | cloudflared |

---

## Node Scheduling

| Pool | Taint | Runs |
|---|---|---|
| Masters | `node-role.kubernetes.io/control-plane:NoSchedule` | k3s control plane only |
| Infra workers | `workload=infra:NoSchedule` | All platform tooling |
| App workers | — | User workloads |

DaemonSets (node-exporter, Longhorn manager, Promtail) use `operator: Exists` to run on all nodes regardless of taint value.

---

## Secrets

All credentials are injected at runtime via environment variables. No secrets are committed to the repository.

The intended production flow:

```
Vault ──► External Secrets Operator ──► Kubernetes Secrets
```

---

## Maintenance

**Upgrade a Helm chart** — edit `version` in `helm/<chart>/Chart.yaml`, commit, ArgoCD syncs automatically.

**Upgrade k3s** — update `version` in `ansible/02-k3s/manifests/upgrade-plans.yaml`, apply with `kubectl apply -f`. The system-upgrade-controller handles the rolling upgrade.

**Add an application** — create `helm/<app>/` with `Chart.yaml` + `values.yaml`, add an ArgoCD Application in `argocd/apps/`, push.

**Scale workers** — edit the node map in `k8s-workers-app.tf` or `k8s-workers-infra.tf`, run `terraform apply`, re-run the k3s playbook.

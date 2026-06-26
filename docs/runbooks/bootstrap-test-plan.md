# Bootstrap Test Plan

This plan is for validating the Proxmox platform bootstrap end to end, including a possible controlled rebuild of the lab guests.

The current preferred strategy is **safe-first**:

1. Run read-only/static checks.
2. Run a Terraform plan against the live Proxmox API.
3. Apply only reviewed non-destructive or accepted changes.
4. Run Ansible bootstrap phases one by one.
5. Verify runtime state after each layer.
6. Only recreate guests after a deliberate destructive checkpoint.

## Safety Rules

- Do not run `terraform destroy`, `terraform apply -destroy`, `terraform state rm`, `terraform state mv`, or `terraform force-unlock` without an explicit checkpoint.
- Do not print `secrets.sh`, `terraform.tfvars`, Terraform state, Vault unseal keys, Proxmox API tokens, GitLab tokens, Harbor robot passwords, kubeconfigs, or private keys.
- Prefer `terraform plan -out=<file>` and apply the exact reviewed plan file.
- Keep the Ubuntu template, downloaded images and SDN as reusable bootstrap substrate unless the test specifically targets those layers.
- Use `scripts/shutdown.sh --guests-only` for a graceful guest stop; the default still powers off the Proxmox host.

## Phase 0 — Local Preflight

```bash
scripts/bootstrap-preflight.sh
```

This checks tools, secrets presence, Proxmox API/SSH reachability, SSH public key, Terraform validation, Helm linting, Ansible syntax and project-specific validators.

For a live read-only Terraform plan:

```bash
scripts/bootstrap-preflight.sh --plan --plan-file tfplan.bootstrap-test
```

Expected result before any rebuild:

- Proxmox API reachable.
- Terraform validates.
- Helm/Ansible/static validators pass.
- Plan is reviewed for adds/changes/destroys.

## Phase 1 — Baseline Current Infrastructure

Collect evidence before changing anything:

```bash
terraform state list
terraform plan -parallelism=2 -out=tfplan.baseline
```

On the Proxmox host, verify expected guest IDs/names:

| ID | Name | Type | Purpose |
|---:|---|---|---|
| 200 | dns | LXC | CoreDNS |
| 201 | k8s-master-1 | VM | k3s control plane |
| 202 | k8s-master-2 | VM | k3s control plane |
| 203 | k8s-master-3 | VM | k3s control plane |
| 204 | k8s-infra-1 | VM | infra worker |
| 205 | k8s-infra-2 | VM | infra worker |
| 206 | k8s-infra-3 | VM | infra worker |
| 207 | k8s-app-1 | VM | app worker |
| 208 | k8s-app-2 | VM | app worker |
| 210 | db-1 | VM | PostgreSQL/Patroni |
| 211 | db-2 | VM | PostgreSQL/Patroni |
| 213 | db-3 | VM | PostgreSQL/Patroni witness/no-failover node |
| 220 | harbor | VM | registry |
| 221 | vault | LXC | secrets |
| 222 | gitlab | VM | source control/project API |
| 230 | tailscale | LXC | subnet router |
| 9000 | ubuntu-2404-template | VM template | reusable VM template |

## Phase 2 — Apply Non-Destructive Drift Fixes

If the plan only shows accepted in-place updates, apply the reviewed plan:

```bash
terraform apply tfplan.bootstrap-test
```

Typical safe candidates:

- provider metadata such as `overwrite=false` on downloaded images;
- memory adjustments for infra workers/GitLab/Harbor, if the Proxmox host has capacity and VM reboot behavior is understood.

Do not apply if the plan includes unexpected destroy/recreate actions.

## Phase 3 — Rebuild Guests Only, If We Intentionally Want a Clean Bootstrap Test

This is destructive for the lab guests. It preserves the base template/downloads/SDN so we test most of the bootstrap without re-downloading substrate.

Checkpoint before running:

```bash
terraform state list > terraform-state-before-rebuild.txt
scripts/shutdown.sh --guests-only
```

Targeted destroy command for guests:

```bash
terraform destroy \
  -target=module.k8s \
  -target=module.workers_infra \
  -target=module.workers_app \
  -target=module.db \
  -target=module.harbor \
  -target=module.gitlab \
  -target=module.dns \
  -target=module.vault \
  -target=module.tailscale \
  -parallelism=2
```

Then recreate:

```bash
terraform plan -parallelism=2 -out=tfplan.recreate
terraform apply tfplan.recreate
```

Expected result: all guest IDs in the inventory table exist again and match the intended IPs.

## Phase 4 — Ansible Bootstrap Sequence

Run one phase at a time and verify after each:

```bash
cd ansible
ansible-playbook 01-prepare_vms/playbook.yml -i 01-prepare_vms/inventory/hosts.yml
ansible-playbook 02-k3s/site.yml -i 02-k3s/inventory/hosts.yml
ansible-playbook 03-postgres/playbook.yml -i 03-postgres/inventory/hosts.yml
ansible-playbook 05-dns/playbook.yml -i 05-dns/inventory/hosts.yml
ansible-playbook 07-vault/site.yml -i 07-vault/inventory/hosts.yml
ansible-playbook 08-vault-k3s/site.yml -i 08-vault-k3s/inventory/hosts.yml
ansible-playbook 04-harbor/playbook.yml -i 04-harbor/inventory/hosts.yml
ansible-playbook 09-gitlab/site.yml -i 09-gitlab/inventory/inventory.yml
ansible-playbook 06-tailscale/site.yml -i 06-tailscale/inventory/hosts.yml
```

## Phase 5 — Kubernetes Recovery Layer

Install or verify Gateway API, Traefik, Longhorn and ArgoCD as the recovery layer, then apply the app-of-apps:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.1/standard-install.yaml
helm dependency build helm/traefik/
helm upgrade --install traefik helm/traefik/ --namespace traefik --create-namespace -f helm/traefik/values.yaml --wait --timeout 3m
helm dependency build helm/longhorn/
helm upgrade --install longhorn helm/longhorn/ --namespace longhorn-system --create-namespace -f helm/longhorn/values.yaml --wait --timeout 5m
helm dependency build helm/argocd/
helm upgrade --install argocd helm/argocd/ --namespace argocd --create-namespace -f helm/argocd/values.yaml --wait --timeout 5m
kubectl apply -f argocd/apps/root.yaml
```

## Phase 6 — GitLab/Jenkins/Harbor End-to-End Test

1. Create/store GitLab Terraform token in Vault.
2. Run `terraform-gitlab` plan/apply.
3. Import/push this repository to `platform/proxmox`.
4. Trigger Jenkins PgBouncer build.
5. Confirm the image is pushed to Harbor.
6. Confirm ArgoCD/k3s pulls the Harbor image.

## Success Criteria

- Terraform plan/apply converges with no unexpected destroy/recreate.
- All Ansible playbooks complete idempotently on a second run.
- k3s nodes are Ready and labels/taints are correct.
- PostgreSQL/Patroni has a healthy leader and replicas.
- CoreDNS resolves `*.proxmox.local` names.
- Vault is reachable internally and Kubernetes auth/ESO prerequisites exist.
- Harbor UI/API works and exposes the `platform` project.
- GitLab health endpoint returns HTTP 200.
- Jenkins JCasC loads and Kubernetes agents can start.
- ArgoCD apps sync successfully.
- PgBouncer image path demonstrates GitLab -> Jenkins -> Harbor -> ArgoCD -> k3s.

## Current Known Plan Pitfalls

- Downloaded image resources should use `overwrite=false` with `prevent_destroy`; otherwise upstream cloud image size changes can produce a blocked replacement plan.
- k3s VIP/load-balancer addresses may appear as out-of-band `ipv4_addresses` drift in Terraform refresh. Treat those as observed guest runtime addresses, not necessarily infrastructure drift.

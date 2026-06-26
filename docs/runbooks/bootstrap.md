# Bootstrap Runbook

This runbook describes the intended company-grade bootstrap order for the Proxmox platform.

> The commands below are the operating sequence. Do not blindly run destructive steps against an existing environment without checking Terraform plan output, Ansible target inventories and current service health.

## 0. Prerequisites

- Proxmox VE 8.x node reachable from the operator machine.
- Terraform >= 1.3.
- Ansible >= 2.15.
- Helm and kubectl.
- Vault CLI if retrieving bootstrap secrets from Vault.
- SSH public key configured in `terraform.tfvars`.
- Tailscale account and Cloudflare-managed domain if public/private access layers are enabled.

## 1. Prepare local secrets

```bash
cp terraform.tfvars.example terraform.tfvars
cp secrets.sh.example secrets.sh  # if/when the example exists
source secrets.sh
```

Required bootstrap values include Proxmox API token/passwords, PostgreSQL/Harbor/GitLab bootstrap credentials, Vault unseal/admin material and Tailscale pre-auth key.

Never commit `secrets.sh`, `terraform.tfvars`, Terraform state, Vault unseal keys or service tokens.

## 2. Provision Proxmox infrastructure

```bash
terraform init
terraform plan -out=tfplan -parallelism=2
terraform apply tfplan
```

Expected result:

- k3s master/worker VMs exist.
- PostgreSQL VMs exist.
- Harbor VM exists.
- GitLab VM exists.
- CoreDNS, Vault and Tailscale LXCs exist.
- Private network and IPs match the README inventory.

## 3. Prepare VMs

```bash
cd ansible
ansible-playbook 01-prepare_vms/playbook.yml -i 01-prepare_vms/inventory/hosts.yml
```

Expected result: base VM access and guest prerequisites are ready.

## 4. Bootstrap k3s

```bash
ansible-playbook 02-k3s/site.yml -i 02-k3s/inventory/hosts.yml
```

Expected result:

- three k3s control-plane nodes are joined;
- infra/app workers are joined;
- kube-vip provides the API VIP;
- nodes are labelled/tainted according to the scheduling model.

## 5. Configure PostgreSQL HA

```bash
ansible-playbook 03-postgres/playbook.yml -i 03-postgres/inventory/hosts.yml
```

Expected result: Patroni, etcd and the PostgreSQL VIP are operational.

## 6. Configure CoreDNS

```bash
ansible-playbook 05-dns/playbook.yml -i 05-dns/inventory/hosts.yml
```

Expected result: internal `proxmox.local` names resolve, including platform service names.

## 7. Configure Vault

```bash
ansible-playbook 07-vault/site.yml -i 07-vault/inventory/hosts.yml
```

Expected result: Vault is installed and reachable only through the intended internal path. Retrieve and store `/root/vault-init.json` securely if this is first initialization.

## 8. Configure Vault Kubernetes auth / External Secrets prerequisites

```bash
ansible-playbook 08-vault-k3s/site.yml -i 08-vault-k3s/inventory/hosts.yml
```

Expected result: Kubernetes auth and platform read policies are available for External Secrets and platform services.

## 9. Configure Harbor

```bash
ansible-playbook 04-harbor/playbook.yml -i 04-harbor/inventory/hosts.yml
```

Expected result:

- Harbor is reachable at `harbor.proxmox.local`.
- Harbor uses the intended external PostgreSQL backend.
- Trivy scanning is available.
- Project `platform` and robot credentials can be prepared for Jenkins.

## 10. Configure GitLab

```bash
export VAULT_GITLAB_ROOT_PASSWORD="$(vault kv get -field=root_password kv/gitlab/admin)"
ansible-playbook 09-gitlab/site.yml -i 09-gitlab/inventory/inventory.yml
```

Expected result:

- GitLab CE runs at `http://gitlab.proxmox.local`.
- SSH is exposed on the configured internal port.
- Container registry is intentionally not the primary registry; Harbor is the runtime artifact registry.

## 11. Configure Tailscale LXC subnet router

1. Apply `docs/tailscale-acl.hujson` in the Tailscale ACL editor.
2. Generate a tagged pre-auth key for `tag:subnet-router`.
3. Export it as `VAULT_TAILSCALE_AUTH_KEY`.
4. Run:

```bash
ansible-playbook 06-tailscale/site.yml -i 06-tailscale/inventory/hosts.yml
```

Expected result: the `10.10.0.0/24` route is advertised and approved.

## 12. Bootstrap recovery layer: Traefik, Longhorn, ArgoCD

Install Gateway API CRDs, Traefik, Longhorn and ArgoCD manually as the recovery layer. These components should remain recoverable even if ArgoCD desired state breaks.

```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.1/standard-install.yaml

helm dependency build helm/traefik/
helm upgrade --install traefik helm/traefik/ \
  --namespace traefik --create-namespace \
  -f helm/traefik/values.yaml \
  --wait --timeout 3m

helm dependency build helm/longhorn/
helm upgrade --install longhorn helm/longhorn/ \
  --namespace longhorn-system --create-namespace \
  -f helm/longhorn/values.yaml \
  --wait --timeout 5m

ARGO_PWD="<password>"
ARGO_HASH=$(htpasswd -nbBC 10 "" "$ARGO_PWD" | tr -d ':\n' | sed 's/$2y/$2a/')
helm dependency build helm/argocd/
helm upgrade --install argocd helm/argocd/ \
  --namespace argocd --create-namespace \
  -f helm/argocd/values.yaml \
  --set argo-cd.configs.secret.argocdServerAdminPassword="$ARGO_HASH" \
  --wait --timeout 5m
```

## 13. Let GitOps take over

```bash
kubectl apply -f argocd/apps/root.yaml
```

Expected result: ArgoCD reconciles the app-of-apps tree and sync waves.

## 14. Deploy Jenkins

Jenkins is managed by Helm/JCasC and should be deployed only after Vault/ESO prerequisites are available.

```bash
helm dependency build helm/jenkins/
helm upgrade --install jenkins helm/jenkins/ \
  --namespace jenkins --create-namespace \
  -f helm/jenkins/values.yaml \
  --wait --timeout 10m
```

Expected result:

- Jenkins UI available at `jenkins.proxmox.local`.
- JCasC loads without manual UI drift.
- Git, Vault and Harbor credentials are sourced from External Secrets.
- Kubernetes agents can start.

## 15. Configure GitLab objects with Terraform

After GitLab is reachable and a Terraform bootstrap token exists in Vault:

```bash
export TF_VAR_gitlab_token="$(vault kv get -field=token kv/gitlab/terraform)"
cd terraform-gitlab
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Expected result:

- `platform` group exists.
- platform repositories exist.
- main branch protection and project hooks are applied where configured.

## 16. First end-to-end image build

1. Push/import this repository into `platform/proxmox`.
2. Ensure Jenkins has Harbor robot credentials.
3. Run `docker/pgbouncer-build`.
4. Verify image exists in Harbor.
5. Verify `helm/pgbouncer/values.yaml` points at the Harbor image.
6. Sync PgBouncer in ArgoCD.
7. Verify PgBouncer pods are ready and pull from Harbor.

## 17. Validation gate

Run before committing or applying changes:

```bash
./scripts/validate.sh
```

Expected result: Terraform, Helm, Ansible syntax and static validators pass. Optional tools such as gitleaks, tflint and ansible-lint should run when installed.

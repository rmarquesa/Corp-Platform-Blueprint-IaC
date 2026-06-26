#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_PLAN=false
PLAN_FILE="tfplan.bootstrap-test"
PROXMOX_HOST_DEFAULT="192.168.1.60"
PROXMOX_ENDPOINT_DEFAULT="https://${PROXMOX_HOST_DEFAULT}:8006/"

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap-preflight.sh [--plan] [--plan-file FILE]

Safe bootstrap preflight for the Proxmox platform.

Default mode is read-only/static:
  - checks required local tools
  - checks secrets are present without printing values
  - checks Proxmox API/SSH reachability
  - checks SSH public key presence
  - runs Terraform fmt/validate
  - runs the repository validation suite

Optional:
  --plan           Run a non-destructive Terraform plan and write a plan file.
  --plan-file FILE Plan output path. Default: tfplan.bootstrap-test

This script never runs terraform apply, destroy, state mutation, or Ansible changes.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan)
      RUN_PLAN=true
      shift
      ;;
    --plan-file)
      PLAN_FILE="${2:?missing value for --plan-file}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWARN: %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

require_tool() {
  local tool="$1"
  have "$tool" || fail "required tool not found: $tool"
  printf 'ok    %s\n' "$tool"
}

secret_status() {
  local var="$1"
  if [[ -n "${!var:-}" ]]; then
    printf 'set   %s\n' "$var"
  else
    printf 'MISS  %s\n' "$var"
    return 1
  fi
}

log "Required tools"
for tool in terraform ansible-playbook helm kubectl python3 curl nc; do
  require_tool "$tool"
done
for optional in gitleaks tflint ansible-lint shellcheck; do
  if have "$optional"; then
    printf 'ok    %s (optional)\n' "$optional"
  else
    warn "$optional not installed; optional check will be skipped"
  fi
done

log "Secret bootstrap file and environment"
[[ -f secrets.sh ]] || fail "secrets.sh not found"
# shellcheck disable=SC1091
source ./secrets.sh >/dev/null 2>&1 || fail "failed to source secrets.sh"
missing=0
for var in \
  TF_VAR_proxmox_api_token \
  TF_VAR_proxmox_ssh_password \
  VAULT_GITLAB_ROOT_PASSWORD \
  VAULT_HARBOR_ADMIN_PASSWORD \
  VAULT_TAILSCALE_AUTH_KEY; do
  secret_status "$var" || missing=1
done
[[ "$missing" -eq 0 ]] || fail "one or more required bootstrap secrets are missing"

log "Local files"
[[ -f .terraform.lock.hcl ]] && printf 'ok    .terraform.lock.hcl\n' || warn ".terraform.lock.hcl missing; terraform init may update providers"
if [[ -f terraform.tfvars ]]; then
  printf 'ok    terraform.tfvars present\n'
else
  warn "terraform.tfvars absent; relying on TF_VAR_* and Terraform defaults"
fi
ssh_key_path="${TF_VAR_ssh_public_key_path:-~/.ssh/rmarquesa.pub}"
ssh_key_path="${ssh_key_path/#\~/$HOME}"
[[ -f "$ssh_key_path" ]] || fail "SSH public key not found: $ssh_key_path"
printf 'ok    ssh public key: %s\n' "$ssh_key_path"

endpoint="${TF_VAR_proxmox_endpoint:-$PROXMOX_ENDPOINT_DEFAULT}"
host="${TF_VAR_proxmox_host:-$PROXMOX_HOST_DEFAULT}"

log "Proxmox reachability: ${host}"
if ping -c 1 -W 1000 "$host" >/dev/null 2>&1; then
  printf 'ok    ping %s\n' "$host"
else
  warn "ping failed for ${host}; continuing to TCP checks"
fi
nc -vz -G 3 "$host" 22 >/dev/null 2>&1 || fail "Proxmox SSH port 22 is not reachable on ${host}"
printf 'ok    tcp %s:22\n' "$host"
nc -vz -G 3 "$host" 8006 >/dev/null 2>&1 || fail "Proxmox API port 8006 is not reachable on ${host}"
printf 'ok    tcp %s:8006\n' "$host"
http_code="$(curl -k -sS --connect-timeout 5 -o /dev/null -w '%{http_code}' "$endpoint")"
[[ "$http_code" =~ ^(200|302|401|403)$ ]] || fail "unexpected Proxmox API HTTP status ${http_code} at ${endpoint}"
printf 'ok    Proxmox API status %s at %s\n' "$http_code" "$endpoint"

log "Terraform workspace/state summary"
terraform workspace show
state_count="$(terraform state list 2>/dev/null | wc -l | tr -d ' ')"
printf 'ok    terraform state resources: %s\n' "$state_count"

log "Terraform fmt/validate"
terraform fmt -check -recursive
terraform validate
if [[ -d terraform-gitlab ]]; then
  terraform -chdir=terraform-gitlab init -backend=false -input=false >/dev/null
  terraform -chdir=terraform-gitlab validate
fi

log "Repository validation suite"
./scripts/validate.sh

if [[ "$RUN_PLAN" == true ]]; then
  log "Terraform plan (non-destructive)"
  set +e
  TF_IN_AUTOMATION=1 terraform plan -no-color -parallelism=2 -detailed-exitcode -out="$PLAN_FILE"
  rc=$?
  set -e
  case "$rc" in
    0)
      printf 'ok    no Terraform changes\n'
      ;;
    2)
      warn "Terraform plan has changes. Review ${PLAN_FILE} before applying."
      ;;
    *)
      fail "terraform plan failed with exit code ${rc}"
      ;;
  esac
fi

log "Preflight complete"

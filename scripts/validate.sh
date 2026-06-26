#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWARN: %s\033[0m\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1; }

log "Terraform fmt check"
terraform fmt -check -recursive

terraform_roots=(".")
if [[ -d terraform-gitlab ]]; then
  terraform_roots+=("terraform-gitlab")
fi

for tf_root in "${terraform_roots[@]}"; do
  log "Terraform validate (${tf_root})"
  if [[ ! -d "${tf_root}/.terraform" ]]; then
    terraform -chdir="${tf_root}" init -backend=false -input=false >/dev/null
  fi
  terraform -chdir="${tf_root}" validate
done

log "Helm lint charts"
while IFS= read -r chart; do
  printf '\n-- %s --\n' "$chart"
  helm lint "$chart"
done < <(find helm -path '*/charts' -prune -o -name Chart.yaml -print | sed 's#/Chart.yaml$##' | sort)

log "Ansible syntax checks"
while IFS= read -r playbook; do
  dir="$(dirname "$playbook")"
  inv=""
  for candidate in \
    "$dir/inventory/hosts.yml" \
    "$dir/inventory/hosts.yaml" \
    "$dir/inventory/inventory.yml" \
    "$dir/inventory/inventory.yaml"; do
    if [[ -f "$candidate" ]]; then
      inv="$candidate"
      break
    fi
  done
  printf '\n-- %s --\n' "$playbook"
  if [[ -n "$inv" ]]; then
    ansible-playbook --syntax-check "$playbook" -i "$inv"
  else
    ansible-playbook --syntax-check "$playbook"
  fi
done < <(find ansible -type f \( -name playbook.yml -o -name site.yml -o -name deploy.yml -o -name upgrade.yml \) | sort)

log "YAML parse check for non-Helm-template files"
python3 - <<'PY'
import os
import sys

try:
    import yaml
except Exception as exc:
    print(f"WARN: PyYAML unavailable, skipping YAML parse check: {exc}")
    sys.exit(0)

skip_dirs = {'.git', '.terraform', '.gpc', 'charts'}
errors = []
count = 0
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    if '/templates' in root.replace('\\', '/') and root.startswith('./helm/'):
        continue
    for name in files:
        if not name.endswith(('.yml', '.yaml')):
            continue
        path = os.path.join(root, name)
        count += 1
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                list(yaml.safe_load_all(fh))
        except Exception as exc:
            errors.append((path, str(exc).splitlines()[0]))

print(f"Parsed {count} YAML files")
if errors:
    for path, err in errors:
        print(f"ERROR: {path}: {err}")
    sys.exit(1)
PY

if need gitleaks; then
  log "Gitleaks scan of tracked/history content"
  gitleaks detect --redact --verbose
else
  warn "gitleaks not installed; skipping secret scan"
fi

if need tflint; then
  log "tflint"
  tflint --recursive
else
  warn "tflint not installed; skipping Terraform lint"
fi

if need ansible-lint; then
  log "ansible-lint"
  ansible-lint ansible
else
  warn "ansible-lint not installed; skipping Ansible lint"
fi

log "Validation complete"

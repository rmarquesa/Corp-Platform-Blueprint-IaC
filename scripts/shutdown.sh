#!/usr/bin/env bash
# Run directly on the Proxmox host: bash /usr/local/sbin/shutdown-guests.sh
set -euo pipefail

TIMEOUT=120  # seconds to wait per guest before forcing off

log() { echo "[$(date '+%H:%M:%S')] $*"; }

wait_stopped() {
  local type=$1 id=$2 name=$3
  local elapsed=0
  while [[ $elapsed -lt $TIMEOUT ]]; do
    local status
    if [[ $type == "vm" ]]; then
      status=$(qm status "$id" | awk '{print $2}')
    else
      status=$(pct status "$id" | awk '{print $2}')
    fi
    [[ $status == "stopped" ]] && return 0
    sleep 5
    elapsed=$((elapsed + 5))
  done
  log "WARN: $name ($id) did not stop in ${TIMEOUT}s — forcing off"
  [[ $type == "vm" ]] && qm stop "$id" || pct stop "$id"
}

shutdown_vm() {
  local id=$1 name=$2
  local status
  status=$(qm status "$id" | awk '{print $2}')
  if [[ $status == "running" ]]; then
    log "Shutting down VM $name ($id)..."
    qm shutdown "$id"
    wait_stopped vm "$id" "$name"
    log "VM $name ($id) stopped."
  else
    log "VM $name ($id) already stopped — skipping."
  fi
}

shutdown_lxc() {
  local id=$1 name=$2
  local status
  status=$(pct status "$id" | awk '{print $2}')
  if [[ $status == "running" ]]; then
    log "Shutting down LXC $name ($id)..."
    pct shutdown "$id"
    wait_stopped lxc "$id" "$name"
    log "LXC $name ($id) stopped."
  else
    log "LXC $name ($id) already stopped — skipping."
  fi
}

log "=== Proxmox graceful shutdown ==="

# 1. k3s app workers — user workloads first
log "--- Step 1: k3s app workers ---"
shutdown_vm 207 k8s-app-1
shutdown_vm 208 k8s-app-2

# 2. k3s infra workers — Longhorn replicas, monitoring
log "--- Step 2: k3s infra workers ---"
shutdown_vm 204 k8s-infra-1
shutdown_vm 205 k8s-infra-2
shutdown_vm 206 k8s-infra-3

# 3. k3s masters — control plane last in k8s
log "--- Step 3: k3s masters ---"
shutdown_vm 203 k8s-master-3
shutdown_vm 202 k8s-master-2
shutdown_vm 201 k8s-master-1

# 4. Harbor registry
log "--- Step 4: Harbor registry ---"
shutdown_vm 220 harbor

# 5. PostgreSQL — replicas before primary
log "--- Step 5: PostgreSQL ---"
shutdown_vm 213 db-3
shutdown_vm 211 db-2
shutdown_vm 210 db-1

# 6. LXC containers — Vault and Tailscale before CoreDNS
log "--- Step 6: LXC containers ---"
shutdown_lxc 221 vault
shutdown_lxc 230 tailscale
shutdown_lxc 200 coredns   # DNS last — needed for resolution during shutdown

log "=== All guests stopped. Powering off host... ==="
sleep 2
poweroff

#!/usr/bin/env python3
"""Static regression checks for Vault being exposed only through local nginx."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "ansible" / "07-vault"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: Path) -> str:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    return path.read_text()


def main() -> None:
    vars_file = read(VAULT / "group_vars" / "all.yml")
    vault_template = read(VAULT / "roles" / "vault" / "templates" / "vault.hcl.j2")
    nginx_template = read(VAULT / "roles" / "vault" / "templates" / "nginx-vault.conf.j2")

    for expected in [
        "vault_listener_address: \"127.0.0.1:8200\"",
        "vault_api_addr: \"http://vault.proxmox.local\"",
        "vault_nginx_proxy_pass: http://127.0.0.1:8200",
    ]:
        if expected not in vars_file:
            fail(f"Vault group_vars missing {expected!r}")

    if 'address     = "{{ vault_listener_address }}"' not in vault_template:
        fail("Vault listener must use vault_listener_address variable")
    if 'address     = "0.0.0.0:8200"' in vault_template or '0.0.0.0:8200' in vars_file:
        fail("Vault must not bind directly to 0.0.0.0:8200")
    if "proxy_pass {{ vault_nginx_proxy_pass }}" not in nginx_template:
        fail("nginx must proxy to configured local Vault listener")

    tasks = read(VAULT / "roles" / "vault" / "tasks" / "main.yml")
    required_order = [
        "Write Vault configuration",
        "Flush Vault handlers before local-only validation",
        "Enable and start Vault",
        "Install nginx for Vault reverse proxy",
        "Enable and start nginx",
        "Check if Vault is initialized",
    ]
    positions = []
    for marker in required_order:
        pos = tasks.find(marker)
        if pos == -1:
            fail(f"Vault tasks missing ordering marker {marker!r}")
        positions.append(pos)
    if positions != sorted(positions):
        fail("Vault/nginx tasks must be ordered so Vault config is applied and nginx is available before Vault status/init uses vault_api_addr")

    print("Vault local-only nginx exposure validation passed")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Static regression checks for Vault's local nginx reverse proxy."""
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
    tasks = read(VAULT / "roles" / "vault" / "tasks" / "main.yml")
    handlers = read(VAULT / "roles" / "vault" / "handlers" / "main.yml")
    vars_file = read(VAULT / "group_vars" / "all.yml")
    nginx_template = read(VAULT / "roles" / "vault" / "templates" / "nginx-vault.conf.j2")

    for expected in ["nginx", "vault_nginx_enabled", "nginx-vault.conf.j2", "sites-enabled", "Enable and start nginx"]:
        if expected not in tasks:
            fail(f"Vault tasks missing {expected!r}")

    if "restart nginx" not in handlers:
        fail("Vault handlers must restart nginx when proxy config changes")

    for expected in ["vault_nginx_enabled: true", "vault_nginx_listen_port: 80", "vault_nginx_proxy_pass: http://127.0.0.1:8200"]:
        if expected not in vars_file:
            fail(f"Vault group_vars missing {expected!r}")

    for expected in [
        "listen {{ vault_nginx_listen_port }}",
        "server_name {{ vault_nginx_server_name }}",
        "proxy_pass {{ vault_nginx_proxy_pass }}",
        "X-Vault-Request",
        "proxy_read_timeout 600s",
        "proxy_send_timeout 600s",
    ]:
        if expected not in nginx_template:
            fail(f"nginx Vault template missing {expected!r}")

    print("Vault nginx proxy static validation passed")


if __name__ == "__main__":
    main()

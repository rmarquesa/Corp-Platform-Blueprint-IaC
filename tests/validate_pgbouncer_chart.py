#!/usr/bin/env python3
"""Static regression checks for the local PgBouncer chart and image."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "pgbouncer"
DOCKERFILE = ROOT / "docker" / "pgbouncer" / "Dockerfile"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: Path) -> str:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    return path.read_text()


def main() -> None:
    chart_yaml = read(CHART / "Chart.yaml")
    if "dependencies:" in chart_yaml or "edoburu.github.io" in chart_yaml:
        fail("PgBouncer chart must be local-only and must not depend on a public PgBouncer chart")

    required_templates = [
        "_helpers.tpl",
        "configmap.yaml",
        "deployment.yaml",
        "service.yaml",
        "secret.yaml",
        "external-secret-userlist.yaml",
        "poddisruptionbudget.yaml",
    ]
    for name in required_templates:
        read(CHART / "templates" / name)

    values = read(CHART / "values.yaml")
    for expected in [
        "repository:",
        "tag:",
        "postgres.proxmox.local",
        "auth_query:",
        "userList:",
        "externalSecrets:",
        "platform/pgbouncer/userlist",
        "nodeSelector:",
        "tolerations:",
    ]:
        if expected not in values:
            fail(f"values.yaml missing expected setting {expected!r}")

    configmap = read(CHART / "templates" / "configmap.yaml")
    for expected in ["[databases]", "[pgbouncer]", "auth_query", "pool_mode"]:
        if expected not in configmap:
            fail(f"configmap template missing {expected!r}")

    deployment = read(CHART / "templates" / "deployment.yaml")
    for expected in ["/etc/pgbouncer/pgbouncer.ini", "userlist.txt", "readinessProbe", "livenessProbe"]:
        if expected not in deployment:
            fail(f"deployment template missing {expected!r}")
    if re.search(r"\n\s+args:\n\s+-\s+/etc/pgbouncer/pgbouncer\.ini", deployment):
        fail("deployment must not append pgbouncer.ini as args when Dockerfile ENTRYPOINT already includes it")

    external_secret = read(CHART / "templates" / "external-secret-userlist.yaml")
    for expected in [
        "kind: ExternalSecret",
        "name: {{ .Values.userList.existingSecret | quote }}",
        "kind: ClusterSecretStore",
        "name: {{ .Values.externalSecrets.clusterSecretStore | quote }}",
        "secretKey: userlist.txt",
        "key: {{ .Values.externalSecrets.userList.remoteKey | quote }}",
        "property: {{ .Values.externalSecrets.userList.property | quote }}",
    ]:
        if expected not in external_secret:
            fail(f"external-secret-userlist template missing {expected!r}")

    dockerfile = read(DOCKERFILE)
    if not re.search(r"^FROM\s+alpine:", dockerfile, flags=re.MULTILINE):
        fail("Dockerfile must be based on alpine")
    for expected in ["apk add", "pgbouncer", "USER pgbouncer", "ENTRYPOINT"]:
        if expected not in dockerfile:
            fail(f"Dockerfile missing {expected!r}")

    print("PgBouncer chart static validation passed")


if __name__ == "__main__":
    main()

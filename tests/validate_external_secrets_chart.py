#!/usr/bin/env python3
"""Static regression checks for External Secrets + Vault integration chart."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "external-secrets"
ARGOCD_APP = ROOT / "argocd" / "apps" / "external-secrets.yaml"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: Path) -> str:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    return path.read_text()


def main() -> None:
    chart = read(CHART / "Chart.yaml")
    values = read(CHART / "values.yaml")
    store = read(CHART / "templates" / "clustersecretstore-vault.yaml")
    auth = read(CHART / "templates" / "vault-tokenreview-clusterrolebinding.yaml")
    app = read(ARGOCD_APP)

    for expected in [
        "name: external-secrets",
        "repository: https://charts.external-secrets.io",
        "version: \"2.4.1\"",
    ]:
        if expected not in chart:
            fail(f"Chart.yaml missing {expected!r}")

    for expected in [
        "installCRDs: true",
        "vault:",
        "server: http://vault.proxmox.local",
        "path: secret",
        "version: v2",
        "mountPath: kubernetes",
        "role: external-secrets",
        "serviceAccountName: external-secrets",
        "createTokenReviewBinding: true",
    ]:
        if expected not in values:
            fail(f"values.yaml missing {expected!r}")

    for expected in [
        "kind: ClusterSecretStore",
        "apiVersion: external-secrets.io/v1",
        "name: vault",
        "server: {{ .Values.vault.server | quote }}",
        "path: {{ .Values.vault.path | quote }}",
        "version: {{ .Values.vault.version | quote }}",
        "mountPath: {{ .Values.vault.kubernetesAuth.mountPath | quote }}",
        "role: {{ .Values.vault.kubernetesAuth.role | quote }}",
        "serviceAccountRef:",
    ]:
        if expected not in store:
            fail(f"ClusterSecretStore template missing {expected!r}")

    for expected in [
        "kind: ClusterRoleBinding",
        "name: external-secrets-vault-tokenreview",
        "system:auth-delegator",
        "kind: ServiceAccount",
        "namespace: {{ .Release.Namespace }}",
    ]:
        if expected not in auth:
            fail(f"TokenReview binding template missing {expected!r}")

    for forbidden in ["root token", "vault-token-secret", "tokenSecretRef", "password:", "secretKey:"]:
        if forbidden.lower() in (chart + values + store + auth).lower():
            fail(f"chart must not contain static Vault credential material or token auth reference: {forbidden!r}")

    for expected in [
        "name: external-secrets",
        "path: helm/external-secrets",
        "namespace: external-secrets",
        "argocd.argoproj.io/sync-wave: \"1\"",
        "CreateNamespace=true",
    ]:
        if expected not in app:
            fail(f"ArgoCD app missing {expected!r}")

    print("External Secrets Vault chart static validation passed")


if __name__ == "__main__":
    main()

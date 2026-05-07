#!/usr/bin/env python3
"""Static regression checks for Vault Kubernetes auth bootstrap (08-vault-k3s).

This validator enforces that:
  1. The dedicated playbook ``ansible/08-vault-k3s`` exists with the expected layout.
  2. ``ansible/08-vault-k3s/group_vars/all.yml`` declares all required Kubernetes
     auth variables (no token / JWT material committed) and a non-secret
     ``kubeconfig`` variable.
  3. ``ansible/08-vault-k3s/roles/vault-k3s/tasks/main.yml`` contains the key
     idempotent tasks (Vault health, enable kubernetes auth, configure mount,
     write policy, create role) and that:
       * every kubectl task carries an ``environment`` block with KUBECONFIG;
       * preflight tasks (``can-i`` + ``get serviceaccount``) run before the
         token generation task;
       * the token generation task keeps ``no_log: true``.
  4. ``ansible/07-vault`` no longer carries any Kubernetes auth wiring:
     - group_vars/all.yml has no ``vault_kubernetes_*`` / ``vault_k8s_*`` /
       ``vault_policy_name`` keys
     - roles/vault/tasks/main.yml has no kubernetes auth tasks
     - roles/vault/templates/kubernetes-platform-read.hcl.j2 is gone
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAULT_07 = ROOT / "ansible" / "07-vault"
VAULT_K3S = ROOT / "ansible" / "08-vault-k3s"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: Path) -> str:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    return path.read_text()


def assert_exists(path: Path) -> None:
    if not path.exists():
        fail(f"expected path missing: {path.relative_to(ROOT)}")


def assert_absent(path: Path) -> None:
    if path.exists():
        fail(f"path must not exist: {path.relative_to(ROOT)}")


def assert_contains(text: str, needle: str, where: str) -> None:
    if needle not in text:
        fail(f"{where} missing {needle!r}")


def assert_not_contains(text: str, needle: str, where: str) -> None:
    if needle in text:
        fail(f"{where} must not contain {needle!r}")


def _split_tasks(tasks_text: str) -> list[str]:
    """Split a tasks file into individual task blocks.

    Tasks start with a top-level ``- name:`` (two-space indent in YAML lists).
    Comments and blank lines between tasks are absorbed into the next task.
    """
    blocks: list[str] = []
    current: list[str] = []
    for line in tasks_text.splitlines():
        if line.startswith("- name:"):
            if current:
                blocks.append("\n".join(current))
                current = []
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    # Drop the leading preamble (everything before the first task).
    return [b for b in blocks if b.lstrip().startswith("- name:")]


def _is_kubectl_task(block: str) -> bool:
    """A task is a kubectl task when it shells out to kubectl via command/argv."""
    if "ansible.builtin.command" not in block and "ansible.builtin.shell" not in block:
        return False
    # Look for the literal kubectl invocation in cmd: / argv: / shell free form.
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "kubectl" in stripped:
            return True
    return False


def _block_has_kubeconfig_env(block: str) -> bool:
    """Verify the block contains an ``environment`` mapping with KUBECONFIG."""
    if "environment:" not in block:
        return False
    # Must reference the kubeconfig var; we don't pin to a specific filter so the
    # check stays robust if expanduser is added/removed, but KUBECONFIG must
    # appear under environment.
    return "KUBECONFIG:" in block and "kubeconfig" in block


def _assert_kubectl_tasks_have_env(role_tasks: Path, tasks_text: str) -> None:
    rel = role_tasks.relative_to(ROOT)
    blocks = _split_tasks(tasks_text)
    kubectl_blocks = [b for b in blocks if _is_kubectl_task(b)]
    if not kubectl_blocks:
        fail(f"{rel} contains no kubectl tasks (expected at least one)")
    for block in kubectl_blocks:
        first_line = block.splitlines()[0]
        if not _block_has_kubeconfig_env(block):
            fail(
                f"{rel} kubectl task {first_line.strip()!r} is missing an "
                f"`environment:` block with KUBECONFIG referencing the "
                f"`kubeconfig` var"
            )


def _task_index(blocks: list[str], needle: str) -> int:
    for idx, block in enumerate(blocks):
        if needle in block:
            return idx
    return -1


def _assert_preflight_before_token_task(role_tasks: Path, tasks_text: str) -> None:
    rel = role_tasks.relative_to(ROOT)
    blocks = _split_tasks(tasks_text)
    sa_idx = _task_index(blocks, "Verify external-secrets serviceaccount exists")
    can_i_idx = _task_index(
        blocks, "Verify permission to create tokens for external-secrets serviceaccount"
    )
    token_idx = _task_index(blocks, "Generate Kubernetes TokenReviewer JWT")
    if sa_idx < 0:
        fail(f"{rel} missing preflight task 'Verify external-secrets serviceaccount exists'")
    if can_i_idx < 0:
        fail(
            f"{rel} missing preflight task "
            f"'Verify permission to create tokens for external-secrets serviceaccount'"
        )
    if token_idx < 0:
        fail(f"{rel} missing 'Generate Kubernetes TokenReviewer JWT' task")
    if not (sa_idx < token_idx and can_i_idx < token_idx):
        fail(
            f"{rel} preflight tasks must run BEFORE the no_log token generation "
            f"task (sa idx={sa_idx}, can-i idx={can_i_idx}, token idx={token_idx})"
        )
    # Preflight tasks must NOT use no_log (they need visible output on failure).
    for label, idx in (("sa_check", sa_idx), ("can_i_check", can_i_idx)):
        block = blocks[idx]
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.replace(" ", "") == "no_log:true":
                fail(
                    f"{rel} preflight task {label!r} must not use 'no_log: true' "
                    f"(visible output is required on failure)"
                )


def _assert_token_task_has_no_log(role_tasks: Path, tasks_text: str) -> None:
    rel = role_tasks.relative_to(ROOT)
    blocks = _split_tasks(tasks_text)
    token_idx = _task_index(blocks, "Generate Kubernetes TokenReviewer JWT")
    if token_idx < 0:
        fail(f"{rel} missing 'Generate Kubernetes TokenReviewer JWT' task")
    block = blocks[token_idx]
    has_no_log = False
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.replace(" ", "") == "no_log:true":
            has_no_log = True
            break
    if not has_no_log:
        fail(
            f"{rel} 'Generate Kubernetes TokenReviewer JWT' must keep "
            f"'no_log: true' to avoid leaking the JWT in logs"
        )


def _assert_ca_fallback_and_failfast(role_tasks: Path, tasks_text: str) -> None:
    """Ensure CA resolution has a ConfigMap fallback and a visible fail when empty.

    Background: when ``.clusters[0].cluster.certificate-authority-data`` is empty
    in the active kubeconfig (or absent), Vault would otherwise fall back to the
    in-cluster path ``/var/run/secrets/kubernetes.io/serviceaccount/ca.crt`` which
    does not exist outside a pod. The role must:

      1. Read CA from the active kubeconfig context using ``kubectl config view
         --minify --raw`` so that only the relevant cluster's CA is extracted.
      2. If empty, fall back to the ``kube-root-ca.crt`` ConfigMap in the target
         namespace via ``kubectl -n {{ vault_k8s_namespace }} get configmap
         kube-root-ca.crt -o jsonpath={.data.ca\\.crt}``.
      3. Fail visibly (no_log MUST NOT be set on the fail task) before the Vault
         API ``Configure Kubernetes auth mount`` task when ``_vault_k8s_ca_cert``
         is still empty.
      4. Keep ``no_log: true`` on every task that handles raw CA material.
    """
    rel = role_tasks.relative_to(ROOT)
    blocks = _split_tasks(tasks_text)

    # 1. kubeconfig CA read must use --minify (active context only) and --raw.
    kc_idx = _task_index(blocks, "Read Kubernetes CA cert from kubeconfig")
    if kc_idx < 0:
        fail(f"{rel} missing 'Read Kubernetes CA cert from kubeconfig' task")
    kc_block = blocks[kc_idx]
    if "--minify" not in kc_block:
        fail(
            f"{rel} 'Read Kubernetes CA cert from kubeconfig' must use "
            f"'kubectl config view --minify --raw' so it extracts the active "
            f"context's cluster CA only"
        )
    if "--raw" not in kc_block:
        fail(
            f"{rel} 'Read Kubernetes CA cert from kubeconfig' must pass --raw "
            f"to get the inline CA data"
        )

    # 2. ConfigMap fallback task must exist with a guard for empty kubeconfig CA.
    cm_idx = _task_index(blocks, "Read Kubernetes CA cert from kube-root-ca.crt ConfigMap")
    if cm_idx < 0:
        fail(
            f"{rel} missing fallback task "
            f"'Read Kubernetes CA cert from kube-root-ca.crt ConfigMap' "
            f"that runs when kubeconfig CA data is empty"
        )
    cm_block = blocks[cm_idx]
    for needle in (
        "argv:",
        "get",
        "configmap",
        "kube-root-ca.crt",
        "jsonpath={.data.ca\\.crt}",
        "{{ vault_k8s_namespace }}",
    ):
        if needle not in cm_block:
            fail(
                f"{rel} ConfigMap fallback task must use argv to call "
                f"'kubectl -n {{{{ vault_k8s_namespace }}}} get configmap "
                f"kube-root-ca.crt -o jsonpath={{.data.ca\\.crt}}' "
                f"so the ca.crt key escape is preserved (missing {needle!r})"
            )
    # The fallback task must be guarded so it only runs when kubeconfig CA is empty.
    if "k8s_ca_b64_result" not in cm_block:
        fail(
            f"{rel} ConfigMap fallback task must be guarded by the kubeconfig "
            f"CA result (when k8s_ca_b64_result.stdout is empty)"
        )
    if "k8s_ca_b64_result.stdout | default('')" not in cm_block:
        fail(
            f"{rel} ConfigMap fallback task must guard kubeconfig CA access "
            f"with default('') so skipped registers do not raise undefined "
            f"attribute errors"
        )
    # Must keep CA material out of logs.
    if "no_log: true" not in cm_block:
        fail(
            f"{rel} ConfigMap fallback task must use 'no_log: true' to avoid "
            f"leaking CA material in logs"
        )
    # Must export the result of the configmap call to a register so the next
    # set_fact can consume it.
    if "register:" not in cm_block:
        fail(
            f"{rel} ConfigMap fallback task must register its result so the "
            f"CA fact can consume the fallback value"
        )

    # 3. Visible fail-fast task when CA is still empty must precede the Vault
    #    'Configure Kubernetes auth mount' task.
    fail_idx = _task_index(blocks, "Fail if Kubernetes CA cert is empty")
    cfg_idx = _task_index(blocks, "Configure Kubernetes auth mount")
    if fail_idx < 0:
        fail(
            f"{rel} missing visible fail task 'Fail if Kubernetes CA cert is "
            f"empty' that aborts before Vault is configured with no CA"
        )
    if cfg_idx < 0:
        fail(f"{rel} missing 'Configure Kubernetes auth mount' task")
    if not (fail_idx < cfg_idx):
        fail(
            f"{rel} 'Fail if Kubernetes CA cert is empty' must run BEFORE "
            f"'Configure Kubernetes auth mount' (fail idx={fail_idx}, "
            f"cfg idx={cfg_idx})"
        )
    fail_block = blocks[fail_idx]
    # Fail message must be visible (no no_log: true).
    for line in fail_block.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.replace(" ", "") == "no_log:true":
            fail(
                f"{rel} 'Fail if Kubernetes CA cert is empty' must NOT use "
                f"'no_log: true' (operator needs to see the error)"
            )
    # Fail message must reference the resolved CA fact name in its when guard.
    if "_vault_k8s_ca_cert" not in fail_block:
        fail(
            f"{rel} 'Fail if Kubernetes CA cert is empty' must guard on "
            f"'_vault_k8s_ca_cert' being empty/undefined"
        )


def _assert_fail_tasks_do_not_leak_secrets(role_tasks: Path, tasks_text: str) -> None:
    """Ensure visible 'Fail on ...' tasks never reference secret material.

    Sensitive Vault API tasks keep ``no_log: true`` but pair with a visible
    ``ansible.builtin.fail`` task that reports only status/msg/json.errors. The
    fail task itself must NOT reference token/CA/header variables, otherwise
    the sanitization is defeated.
    """
    rel = role_tasks.relative_to(ROOT)
    blocks = _split_tasks(tasks_text)
    sensitive_strings = [
        "token_reviewer_jwt",
        "kubernetes_ca_cert",
        "X-Vault-Token",
        "vault_token",
        "_vault_token_reviewer_jwt",
        "_vault_k8s_ca_cert",
    ]
    fail_blocks = [b for b in blocks if "Fail on " in b.splitlines()[0]]
    if not fail_blocks:
        fail(
            f"{rel} expected at least one 'Fail on ...' visible task pairing "
            f"with the no_log Vault API tasks"
        )
    for block in fail_blocks:
        first_line = block.splitlines()[0].strip()
        for needle in sensitive_strings:
            if needle in block:
                fail(
                    f"{rel} fail task {first_line!r} must not reference "
                    f"secret material {needle!r} in its message/when clause"
                )


def main() -> None:
    # ---- Step 1: ansible/08-vault-k3s structure exists ----
    site_yml = VAULT_K3S / "site.yml"
    inv_hosts = VAULT_K3S / "inventory" / "hosts.yml"
    gv_all = VAULT_K3S / "group_vars" / "all.yml"
    role_tasks = VAULT_K3S / "roles" / "vault-k3s" / "tasks" / "main.yml"
    role_template = (
        VAULT_K3S / "roles" / "vault-k3s" / "templates" / "kubernetes-platform-read.hcl.j2"
    )

    for required in (site_yml, inv_hosts, gv_all, role_tasks, role_template):
        assert_exists(required)

    # ---- Step 2: required Kubernetes auth vars in 08-vault-k3s/group_vars/all.yml ----
    gv_text = read(gv_all)
    for expected in [
        "vault_addr:",
        "vault_addr: \"http://vault.proxmox.local\"",
        "vault_k8s_auth_mount:",
        "vault_k8s_host:",
        "vault_k8s_auth_role:",
        "vault_k8s_service_account:",
        "vault_k8s_namespace:",
        "vault_k8s_token_ttl:",
        "vault_policy_name:",
        "vault_k8s_disable_iss_validation:",
        # Non-secret kubeconfig var so kubectl tasks honor a deterministic path.
        "kubeconfig:",
    ]:
        assert_contains(gv_text, expected, "08-vault-k3s/group_vars/all.yml")

    # The kubeconfig var must come from KUBECONFIG env (with a sane default),
    # never a hard-coded admin path that bypasses operator preference.
    assert_contains(
        gv_text,
        "lookup('env', 'KUBECONFIG')",
        "08-vault-k3s/group_vars/all.yml (kubeconfig must honor KUBECONFIG env)",
    )

    # Vault validates the Kubernetes API server certificate when it performs
    # TokenReview. Rodrigo's kubeconfig uses k8s-api.proxmox.local with
    # insecure-skip-tls-verify, but the real API cert is valid for the kube-vip
    # address. Do not configure Vault with the kubeconfig hostname, otherwise
    # ESO login fails with Vault Kubernetes auth 403 permission denied.
    assert_contains(
        gv_text,
        'vault_k8s_host: "https://10.10.0.100:6443"',
        "08-vault-k3s/group_vars/all.yml (Vault Kubernetes auth host must use kube-vip IP with valid TLS SAN)",
    )
    assert_not_contains(
        gv_text,
        "https://k8s-api.proxmox.local:6443",
        "08-vault-k3s/group_vars/all.yml (kubeconfig hostname is not valid for Vault TLS verification)",
    )

    # No token/JWT/secret material may be committed.
    forbidden_in_vars = [
        "vault_token:",  # admin token must come from -e or VAULT_TOKEN
        "vault_kubernetes_token_reviewer_jwt:",
        "hvs.",
        "eyJ",  # JWT prefix
        "root_token",
    ]
    for item in forbidden_in_vars:
        # Allow these strings only if they appear inside a comment line.
        for line in gv_text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if item in stripped:
                fail(
                    f"08-vault-k3s/group_vars/all.yml must not commit secret material "
                    f"or runtime-only var {item!r}"
                )

    # ---- Step 3: required task names in 08-vault-k3s/roles/vault-k3s/tasks/main.yml ----
    tasks_text = read(role_tasks)
    for expected in [
        "Check Vault health",
        "Fail if Vault is sealed or unreachable",
        "Check if Kubernetes auth mount exists",
        "Enable Kubernetes auth method",
        "Configure Kubernetes auth mount",
        "Write Vault policy kubernetes-platform-read",
        "Create Vault Kubernetes auth role",
        "no_log: true",
        "ansible.builtin.uri",
        "X-Vault-Token",
        "{{ vault_addr }}/v1/sys/health",
        "{{ vault_addr }}/v1/sys/auth/{{ vault_k8s_auth_mount }}",
        "{{ vault_addr }}/v1/auth/{{ vault_k8s_auth_mount }}/config",
        "{{ vault_addr }}/v1/sys/policies/acl/{{ vault_policy_name }}",
        "{{ vault_addr }}/v1/auth/{{ vault_k8s_auth_mount }}/role/{{ vault_k8s_auth_role }}",
        # Preflight checks that must run before the no_log token task so a
        # misconfigured KUBECONFIG / RBAC failure surfaces with visible output.
        "Verify external-secrets serviceaccount exists",
        "Verify permission to create tokens for external-secrets serviceaccount",
        "kubectl auth can-i create serviceaccounts/token",
        "get serviceaccount {{ vault_k8s_service_account }}",
        # Token generation task must keep its no_log + namespaced create token call.
        "Generate Kubernetes TokenReviewer JWT",
        "create token {{ vault_k8s_service_account }} --duration=8760h",
        # Sanitized error surfacing for sensitive Vault API tasks: each sensitive
        # call must register a result, swallow Ansible's default failure, and be
        # paired with a visible fail task that reports only status/msg/errors.
        "vault_k8s_config_result",
        "Fail on Configure Kubernetes auth mount error",
        "vault_policy_result",
        "Fail on Write Vault policy error",
        "vault_role_result",
        "Fail on Create Vault Kubernetes auth role error",
        "disable_iss_validation",
        "failed_when: false",
        # CA resolution: kubeconfig (active context only) with ConfigMap fallback
        # and a visible fail-fast before the Vault auth-mount config task.
        "--minify",
        "Read Kubernetes CA cert from kube-root-ca.crt ConfigMap",
        "kube-root-ca.crt",
        "jsonpath={.data.ca\\.crt}",
        "Fail if Kubernetes CA cert is empty",
    ]:
        assert_contains(
            tasks_text, expected, "08-vault-k3s/roles/vault-k3s/tasks/main.yml"
        )

    # ---- Step 3a: every kubectl invocation must set KUBECONFIG via environment ----
    _assert_kubectl_tasks_have_env(role_tasks, tasks_text)

    # ---- Step 3b: preflight tasks must precede the (no_log) token generation ----
    _assert_preflight_before_token_task(role_tasks, tasks_text)

    # ---- Step 3c: the token generation task must keep no_log: true ----
    _assert_token_task_has_no_log(role_tasks, tasks_text)

    # ---- Step 3d: visible fail tasks must not leak secrets ----
    _assert_fail_tasks_do_not_leak_secrets(role_tasks, tasks_text)

    # ---- Step 3e: CA resolution must have a kube-root-ca.crt ConfigMap fallback
    #               and a visible fail-fast before the Vault config task. ----
    _assert_ca_fallback_and_failfast(role_tasks, tasks_text)

    # Policy template content sanity check
    policy_text = read(role_template)
    for expected in [
        'path "kv/data/platform/*"',
        'capabilities = ["read"]',
        'path "kv/metadata/platform/*"',
        'capabilities = ["read", "list"]',
        'path "kv/data/jenkins/*"',
        'path "kv/metadata/jenkins/*"',
    ]:
        assert_contains(
            policy_text,
            expected,
            "08-vault-k3s/roles/vault-k3s/templates/kubernetes-platform-read.hcl.j2",
        )

    # site.yml + inventory sanity
    site_text = read(site_yml)
    for expected in [
        "hosts: localhost",
        "connection: local",
        "VAULT_TOKEN",
        "vault_token must be provided",
        "- vault-k3s",
    ]:
        assert_contains(site_text, expected, "08-vault-k3s/site.yml")

    inv_text = read(inv_hosts)
    assert_contains(inv_text, "localhost:", "08-vault-k3s/inventory/hosts.yml")
    assert_contains(inv_text, "ansible_connection: local", "08-vault-k3s/inventory/hosts.yml")

    # ---- Step 4: 07-vault/group_vars/all.yml has NO kubernetes auth vars ----
    vault07_vars = read(VAULT_07 / "group_vars" / "all.yml")
    forbidden_vars_in_07 = [
        "vault_kubernetes_auth_enabled",
        "vault_kubernetes_auth_mount",
        "vault_kubernetes_auth_role",
        "vault_kubernetes_auth_policy",
        "vault_kubernetes_auth_bound_service_account_names",
        "vault_kubernetes_auth_bound_service_account_namespaces",
        "vault_kubernetes_host",
        "vault_kubernetes_auth_ttl",
        "vault_kubernetes_ca_cert_path",
        "vault_kubernetes_token_reviewer_jwt",
        "vault_k8s_auth_mount",
        "vault_k8s_host",
        "vault_k8s_auth_role",
        "vault_k8s_service_account",
        "vault_k8s_namespace",
        "vault_k8s_token_ttl",
        "vault_policy_name",
    ]
    for item in forbidden_vars_in_07:
        assert_not_contains(vault07_vars, item, "07-vault/group_vars/all.yml")

    # ---- Step 5: 07-vault tasks/main.yml has NO kubernetes auth tasks ----
    vault07_tasks = read(VAULT_07 / "roles" / "vault" / "tasks" / "main.yml")
    forbidden_tasks_in_07 = [
        "kubernetes-platform-read",
        "vault auth enable",
        "vault auth list",
        "vault_kubernetes_auth_mount",
        "vault_kubernetes_auth_role",
        "vault_kubernetes_auth_policy",
        "vault_kubernetes_token_reviewer_jwt",
        "vault_kubernetes_host",
        "vault_kubernetes_ca_cert_path",
        "token_reviewer_jwt",
        "kubernetes_ca_cert",
        "kubernetes_host",
        "bound_service_account_names",
        "bound_service_account_namespaces",
    ]
    for item in forbidden_tasks_in_07:
        assert_not_contains(vault07_tasks, item, "07-vault/roles/vault/tasks/main.yml")

    # ---- Step 6: 07-vault no longer ships the policy template ----
    assert_absent(VAULT_07 / "roles" / "vault" / "templates" / "kubernetes-platform-read.hcl.j2")

    # Final cross-cutting check: nothing under the new playbook should embed
    # static secret / token material.
    forbidden_globally = ["hvs.", "eyJ", "root_token"]
    for path in (gv_all, site_yml, role_tasks, role_template, inv_hosts):
        text = read(path)
        for item in forbidden_globally:
            for line in text.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if item in stripped:
                    fail(
                        f"{path.relative_to(ROOT)} must not embed token literal "
                        f"or secret material: {item!r}"
                    )

    print("Vault Kubernetes auth (08-vault-k3s) static validation passed")


if __name__ == "__main__":
    main()

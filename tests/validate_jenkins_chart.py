#!/usr/bin/env python3
"""
Static regression checks for the Jenkins Helm wrapper chart.

Catches the three classes of errors that caused boot failures during
Jenkins 2.555.1 migration:
  1. Plugin install failures  (duplicate entries, bad format)
  2. JCasC deprecated/removed keys  (hard boot failure)
  3. JCasC YAML syntax errors  (hard boot failure)

Run:
    python3 tests/validate_jenkins_chart.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "jenkins"
JCASC_DIR = CHART / "jcasc"
VALUES = CHART / "values.yaml"

# ---------------------------------------------------------------------------
# Keys removed from the Jenkins JCasC model in 2.500-2.555 range.
# Any of these in an active JCasC file causes ConfigurationAsCodeBootFailure.
# ---------------------------------------------------------------------------
REMOVED_KEYS: dict[str, str] = {
    "agentProtocols": "removed in Jenkins 2.555.1 — hardcoded to JNLP4-connect+Ping",
    "fingerprints": "removed in Jenkins 2.555.1 — configure via Manage Jenkins UI only",
    "csrf": "top-level csrf key removed; use crumbIssuer inside jenkins:",
    "remotingSecurity": "removed in 2.326 — legacy remoting is always disabled",
}

# ---------------------------------------------------------------------------
# Keys that are still accepted but log a WARNING today and will become fatal.
# ---------------------------------------------------------------------------
DEPRECATED_KEYS: dict[str, str] = {
    # globalMatrix.permissions → globalMatrix.entries (matrix-auth 3.x)
    # Caught separately with context check below.
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fail(msg: str) -> None:
    print(f"FAIL  {msg}", file=sys.stderr)
    raise SystemExit(1)


def warn(msg: str) -> None:
    print(f"WARN  {msg}")


def ok(msg: str) -> None:
    print(f"ok    {msg}")


def read(path: Path) -> str:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    return path.read_text()


def load_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(read(path))
    except yaml.YAMLError as exc:
        fail(f"{path.relative_to(ROOT)}: YAML parse error — {exc}")


def find_keys(obj: object, target: str, _path: str = "") -> list[str]:
    """Return dot-paths of every occurrence of *target* key in the tree."""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{_path}.{k}" if _path else k
            if k == target:
                found.append(here)
            found.extend(find_keys(v, target, here))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            found.extend(find_keys(item, target, f"{_path}[{i}]"))
    return found


# ---------------------------------------------------------------------------
# Check 1 — JCasC file validity
# ---------------------------------------------------------------------------

def check_jcasc() -> None:
    active = sorted(JCASC_DIR.glob("*.yaml"))
    if not active:
        fail(f"no JCasC files found in {JCASC_DIR.relative_to(ROOT)}")

    for path in active:
        rel = path.relative_to(ROOT)
        doc = load_yaml(path)

        # 1a — removed keys cause hard boot failure
        for key, reason in REMOVED_KEYS.items():
            paths = find_keys(doc, key)
            if paths:
                fail(f"{rel}: key '{key}' is removed — {reason}  (found at: {paths})")

        # 1b — globalMatrix must use 'entries', not 'permissions'
        #      (permissions= accepted today but will become fatal in future CasC)
        auth_paths = find_keys(doc, "globalMatrix")
        for ap in auth_paths:
            # Walk to the actual dict node
            node = _get_at_path(doc, ap)
            if isinstance(node, dict) and "permissions" in node and "entries" not in node:
                fail(
                    f"{rel}: globalMatrix uses deprecated 'permissions:' — "
                    "migrate to 'entries:' (matrix-auth 3.x format)"
                )

        ok(f"{rel}")


def _get_at_path(obj: object, dotpath: str) -> object:
    """Navigate a dot-path (e.g. 'jenkins.authorizationStrategy.globalMatrix')."""
    for part in re.split(r"\.|\[(\d+)\]", dotpath):
        if part is None or part == "":
            continue
        if isinstance(obj, dict):
            obj = obj.get(part, {})
        elif isinstance(obj, list):
            obj = obj[int(part)]
        else:
            return {}
    return obj


# ---------------------------------------------------------------------------
# Check 2 — Plugin list in values.yaml
# ---------------------------------------------------------------------------

def check_plugins() -> None:
    values = load_yaml(VALUES)
    plugins: list[str] = (
        values.get("jenkins", {})
              .get("controller", {})
              .get("installPlugins", [])
    )

    if not plugins:
        warn("installPlugins list is empty")
        return

    seen: dict[str, str] = {}
    bad_format: list[str] = []

    for entry in plugins:
        if not isinstance(entry, str):
            fail(f"installPlugins: non-string entry {entry!r}")

        # Expected format: name:version
        if ":" not in entry:
            bad_format.append(entry)
            continue

        name, version = entry.split(":", 1)
        name = name.strip()
        version = version.strip()

        if not name or not version:
            bad_format.append(entry)
            continue

        if name in seen:
            fail(
                f"installPlugins: duplicate plugin '{name}' "
                f"({seen[name]}  vs  {entry})"
            )
        seen[name] = entry

    if bad_format:
        fail(
            f"installPlugins: entries missing 'name:version' format — "
            + ", ".join(bad_format)
        )

    ok(f"installPlugins: {len(plugins)} plugins, no duplicates, all well-formed")


# ---------------------------------------------------------------------------
# Check 3 — Secrets referenced in JCasC exist in additionalExistingSecrets
# ---------------------------------------------------------------------------

def check_secret_refs() -> None:
    """
    JCasC interpolates ${secret-name-key} from secrets mounted at
    /run/secrets/additional/<secret-name>/<key>.  Verify every
    ${jenkins-*} reference in JCasC has a matching additionalExistingSecrets
    entry in values.yaml (or is the admin secret handled separately).
    """
    values = load_yaml(VALUES)
    extra: list[dict] = (
        values.get("jenkins", {})
              .get("controller", {})
              .get("additionalExistingSecrets", [])
    )
    # Build set of "secret-keyName" pairs that are mounted
    mounted: set[str] = set()
    for item in extra:
        name = item.get("name", "")
        key = item.get("keyName", "")
        if name and key:
            mounted.add(f"{name}-{key}")

    # Also include the admin secret (handled via controller.admin.existingSecret)
    admin_secret = (
        values.get("jenkins", {})
              .get("controller", {})
              .get("admin", {})
              .get("existingSecret", "")
    )

    missing: list[str] = []
    for path in sorted(JCASC_DIR.glob("*.yaml")):
        content = read(path)
        # Match ${jenkins-something-something} interpolation variables
        for match in re.finditer(r"\$\{(jenkins-[^}]+)\}", content):
            ref = match.group(1)
            # Admin credentials are mounted differently — skip
            if admin_secret and ref.startswith(admin_secret.replace("jenkins-", "jenkins-")):
                continue
            if ref not in mounted:
                missing.append(f"{path.relative_to(ROOT)}: ${{{ref}}}")

    if missing:
        warn(
            "JCasC references secrets not listed in additionalExistingSecrets "
            "(may fail at runtime if not mounted):\n  "
            + "\n  ".join(missing)
        )
    else:
        ok("JCasC secret interpolation references all covered by additionalExistingSecrets")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("── JCasC files ──────────────────────────────────────────────────")
    check_jcasc()

    print("\n── Plugin list ──────────────────────────────────────────────────")
    check_plugins()

    print("\n── Secret references ────────────────────────────────────────────")
    check_secret_refs()

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()

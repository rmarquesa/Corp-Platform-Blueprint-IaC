# Jenkins Helm Chart

Production-grade Jenkins deployment for the Proxmox k3s platform. Fully declarative, GitOps-friendly, and secret-free at rest.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Stack](#stack)
- [Repository Layout](#repository-layout)
- [Secrets Flow](#secrets-flow)
- [Vault Setup](#vault-setup)
- [JCasC Configuration](#jcasc-configuration)
- [Init Scripts](#init-scripts)
- [Kubernetes Agents](#kubernetes-agents)
- [Plugins](#plugins)
- [Network Policy](#network-policy)
- [Resource Quota](#resource-quota)
- [Bootstrap](#bootstrap)
- [Validation](#validation)
- [Troubleshooting](#troubleshooting)
- [Day-2 Operations](#day-2-operations)
- [Security Notes](#security-notes)

---

## Overview

This chart deploys **Jenkins 2.555.1** as a Kubernetes `StatefulSet` via a thin Helm wrapper around the upstream `jenkins/jenkins` chart (`5.9.18`). The deployment is fully declarative:

- All controller configuration is expressed via **JCasC** (Configuration as Code).
- All secrets are sourced from **HashiCorp Vault** through the **External Secrets Operator** (ESO).
- No manual UI configuration is expected to survive a pod restart. If it is not in Git, it does not exist.

This contract enables clean upgrades, reproducible disaster recovery, and a single source of truth.

---

## Architecture

| Concern              | Implementation                                         |
| -------------------- | ------------------------------------------------------ |
| Workload type        | `StatefulSet` (single replica controller)              |
| Configuration        | Jenkins Configuration as Code (JCasC) ConfigMap        |
| Init logic           | Groovy init scripts ConfigMap (runs before JCasC)      |
| Secret management    | External Secrets Operator + Vault KV v2                |
| Build agents         | Ephemeral pods via the Kubernetes plugin               |
| Ingress              | Traefik to `jenkins.proxmox.local` (HTTP, internal)    |
| Persistent storage   | Longhorn 10Gi PVC for `JENKINS_HOME`                   |
| Cluster              | k3s, service CIDR `10.43.0.0/16`                       |

---

## Stack

| Component             | Version  |
| --------------------- | -------- |
| Jenkins               | 2.555.1  |
| Upstream chart        | 5.9.18   |
| Wrapper chart         | 1.0.0    |
| Namespace             | jenkins  |

---

## Repository Layout

```
helm/jenkins/
|-- Chart.yaml                          # Wrapper, depends on jenkins/jenkins 5.9.18
|-- values.yaml                         # All configuration
|-- templates/
|   |-- configmap-jcasc.yaml            # Renders jcasc/*.yaml -> ConfigMaps labeled jenkins-jenkins-config
|   |-- configmap-init-scripts.yaml     # Renders init-scripts/*.groovy -> ConfigMap
|   |-- external-secret-admin.yaml      # jenkins-admin-secret (ESO)
|   |-- external-secret-git.yaml        # jenkins-git-credentials (ESO)
|   |-- external-secret-vault-approle.yaml  # jenkins-vault-approle (ESO)
|   |-- network-policy.yaml             # Egress/ingress rules for controller + agents
|   `-- resource-quota.yaml             # Namespace quota + LimitRange
|-- jcasc/
|   |-- jenkins.yaml                    # Controller global settings (mode, executors, slaveAgentPort)
|   |-- security.yaml                   # SecurityRealm (local) + GlobalMatrix authz
|   |-- credentials.yaml                # git-credentials + vault-approle-placeholder
|   |-- kubernetes-cloud.yaml           # Kubernetes cloud + agent pod template (docker socket)
|   |-- vault-config.yaml               # Vault plugin endpoint + AppRole credential ref
|   |-- seed-job.yaml                   # Seed pipeline that bootstraps Job DSL
|   |-- script-security.yaml            # Groovy sandbox enforcement
|   `-- welcome-message.yaml            # Dashboard system message
|-- init-scripts/
|   |-- 00-hardening.groovy             # CLI disable, CSRF, quiet period, OldDataMonitor
|   |-- 01-disable-master-executors.groovy  # numExecutors=0 (builds only on agents)
|   |-- 02-agent-protocols.groovy       # Remove legacy JNLP/CLI protocols
|   `-- 03-build-discarder.groovy       # Global log rotation: 30 days / 10 builds
`-- tests/
    `-- validate_jenkins_chart.py        # Static validation (run before helm upgrade)
```

---

## Secrets Flow

All secrets are stored in **HashiCorp Vault KV v2**, materialised into Kubernetes `Secret` objects by ESO, and injected into JCasC through `${variable}` interpolation. **No secret value is ever committed to Git.**

### ExternalSecrets

| Name                      | Vault path                  | Keys                                            |
| ------------------------- | --------------------------- | ----------------------------------------------- |
| `jenkins-admin-secret`    | `kv/jenkins/admin`          | `jenkins-admin-user`, `jenkins-admin-password`  |
| `jenkins-git-credentials` | `kv/jenkins/git`            | `git-username`, `git-password`                  |
| `jenkins-vault-approle`   | `kv/jenkins/vault-approle`  | `vault-role-id`, `vault-secret-id`              |

### Interpolation

Secrets are mounted at `/run/secrets/additional/<secret-name>/<keyName>` and referenced from JCasC YAML as `${secret-name-keyName}` (hyphenated form).

| Setting              | Value                          |
| -------------------- | ------------------------------ |
| ClusterSecretStore   | `vault` (pre-provisioned)      |
| Refresh interval     | `1h`                           |
| Mount root           | `/run/secrets/additional`      |

---

## Vault Setup

A Vault policy and Kubernetes auth role must exist before the chart is installed.

### Policy

```hcl
# policies/jenkins.hcl
path "kv/data/jenkins/*"     { capabilities = ["read"] }
path "kv/metadata/jenkins/*" { capabilities = ["read", "list"] }
```

### Bootstrap

```bash
vault policy write jenkins policies/jenkins.hcl

vault write auth/kubernetes/role/jenkins \
  bound_service_account_names=jenkins \
  bound_service_account_namespaces=jenkins \
  policies=jenkins ttl=1h

vault kv put kv/jenkins/admin         username=<user> password=<pass>
vault kv put kv/jenkins/git           username=<user> password=<token>
vault kv put kv/jenkins/vault-approle role-id=<id>    secret-id=<secret>
```

---

## JCasC Configuration

Files under `jcasc/` are merged into a single ConfigMap and consumed by the JCasC plugin at boot.

### `jenkins.yaml` — Controller globals

| Key                  | Value                |
| -------------------- | -------------------- |
| `mode`               | `NORMAL`             |
| `numExecutors`       | `0` (no builds on controller) |
| `slaveAgentPort`     | `50000` (JNLP4-connect) |
| `markupFormatter`    | `plainText`          |
| `disableRememberMe`  | `false`              |

### `security.yaml`

Local security realm with a single admin user sourced from Vault. Anonymous users have read-only access (`Overall/Read`, `Job/Read`, `View/Read`). Uses `matrix-auth` 3.x `entries:` syntax (not the legacy `permissions:` form).

### `credentials.yaml`

Two global credentials:

| ID                          | Type                                       | Source                       |
| --------------------------- | ------------------------------------------ | ---------------------------- |
| `git-credentials`           | usernamePassword                           | `jenkins-git-credentials`    |
| `vault-approle-placeholder` | vaultAppRoleCredential (path=`approle`)    | `jenkins-vault-approle`      |

### `kubernetes-cloud.yaml`

Kubernetes cloud pointing to `https://kubernetes.default`, namespace `jenkins`. Defines a single pod template `default` with label `jenkins-agent` that mounts `/var/run/docker.sock` from the host for Docker builds. **No Kaniko.**

### `vault-config.yaml`

| Key             | Value                          |
| --------------- | ------------------------------ |
| Vault URL       | `http://vault.proxmox.local`   |
| Engine          | KV v2                          |
| Credential      | `vault-approle-placeholder`    |

### `seed-job.yaml`

Pipeline job named `seed-job` that checks out `https://git.proxmox.local/platform/jenkins-jobs.git` and runs `jobDsl` over `jobs/**/*.groovy` with `removedJobAction: DELETE`.

### Other files

| File                   | Purpose                            |
| ---------------------- | ---------------------------------- |
| `script-security.yaml` | Enforces Groovy sandbox            |
| `welcome-message.yaml` | Dashboard system message           |

---

## Init Scripts

Groovy init scripts run **before** JCasC at controller startup, in lexical order.

| File                                  | Purpose                                                                                                              |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `00-hardening.groovy`                 | Disables CLI-over-Remoting, sets `quietPeriod=0`, disables `OldDataMonitor`, enforces CSRF with `DefaultCrumbIssuer` |
| `01-disable-master-executors.groovy`  | Sets `numExecutors=0` (all builds go to agents)                                                                      |
| `02-agent-protocols.groovy`           | Removes `JNLP-connect`, `JNLP2-connect`, `CLI-connect`; keeps `JNLP4-connect` only                                   |
| `03-build-discarder.groovy`           | Installs a global `LogRotator`: 30 days / 10 builds                                                                  |

---

## Kubernetes Agents

| Setting          | Value                              |
| ---------------- | ---------------------------------- |
| Cloud            | `kubernetes` (in-cluster)          |
| API endpoint     | `https://kubernetes.default`       |
| Namespace        | `jenkins`                          |
| ServiceAccount   | `jenkins-agent`                    |
| Pod template     | `default` (label `jenkins-agent`)  |
| Docker socket    | `/var/run/docker.sock` (hostPath)  |
| Requests         | `200m` CPU / `512Mi` memory        |
| Limits           | `1000m` CPU / `1Gi` memory         |
| `containerCap`   | `10`                               |
| `connectTimeout` | `5s`                               |
| `readTimeout`    | `15s`                              |
| `waitForPodSec`  | `600`                              |

### Pipeline usage

```groovy
pipeline {
  agent { label 'jenkins-agent' }
  stages {
    stage('Build') {
      steps { sh 'docker build -t myapp:${BUILD_NUMBER} .' }
    }
  }
}
```

---

## Plugins

27 primary plugins are declared; transitive dependencies are auto-resolved by the Jenkins plugin manager.

| Category                  | Plugins                                                                                                                                                          |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Configuration & Security  | `antisamy-markup-formatter`, `configuration-as-code`, `credentials`, `credentials-binding`, `matrix-auth`, `role-strategy`, `script-security`, `ssh-credentials` |
| Source Control            | `git`, `github`                                                                                                                                                  |
| Pipelines                 | `pipeline-model-definition`, `pipeline-rest-api`, `pipeline-stage-view`, `workflow-aggregator`, `workflow-multibranch`, `job-dsl`                                |
| Kubernetes Agents         | `kubernetes`, `kubernetes-credentials`, `docker-plugin`                                                                                                          |
| Integrations              | `hashicorp-vault-plugin`, `sonar`, `snyk-security-scanner`                                                                                                       |
| Notifications & UI        | `email-ext`, `mailer`, `junit`, `favorite`, `matrix-project`                                                                                                     |

> **Note:** `overwritePlugins: true` is set, so plugins are re-installed on every restart from this list. Updating a plugin requires changing the version in `values.yaml` and running `helm upgrade`.

---

## Network Policy

### `jenkins-controller`

Applies to pods with label `app.kubernetes.io/component: jenkins-controller`.

| Direction | Ports                              | Purpose                                  |
| --------- | ---------------------------------- | ---------------------------------------- |
| Ingress   | `8080`                             | Traefik HTTP                             |
| Ingress   | `50000` (from `jenkins` namespace) | Agent JNLP4 tunnel                       |
| Egress    | `443`, `6443`                      | k3s API (see warning below)              |
| Egress    | `8200`                             | Vault                                    |
| Egress    | `53` UDP/TCP                       | DNS                                      |

### `jenkins-agents`

Applies to pods with label `jenkins/jenkins-agent: "true"`.

| Direction | Ports                | Purpose                  |
| --------- | -------------------- | ------------------------ |
| Egress    | `50000`, `8080`      | Controller JNLP and HTTP |
| Egress    | `443`, `80`          | External downloads       |
| Egress    | `53`                 | DNS                      |

> **Warning:** k3s DNATs the `kubernetes` service `10.43.0.1:443` to `node:6443` **before** the NetworkPolicy `FORWARD` chain is evaluated. Port `6443` must be explicitly allowed in egress, otherwise the JCasC reload sidecar fails with `ECONNREFUSED`.

---

## Resource Quota

### ResourceQuota `jenkins-quota`

| Resource           | Value |
| ------------------ | ----- |
| `requests.cpu`     | 8     |
| `requests.memory`  | 12Gi  |
| `limits.cpu`       | 16    |
| `limits.memory`    | 24Gi  |
| `pods`             | 20    |

### LimitRange `jenkins-limitrange`

| Direction       | CPU   | Memory |
| --------------- | ----- | ------ |
| Default limit   | 200m  | 512Mi  |
| Default request | 50m   | 64Mi   |

---

## Bootstrap

Pre-requisites that must already be running in the cluster:

- `external-secrets` operator
- HashiCorp Vault (configured with the policy and role above)
- Traefik
- Longhorn

```bash
helm dependency update helm/jenkins
helm upgrade --install jenkins helm/jenkins \
  --namespace jenkins --create-namespace
```

---

## Validation

Run the static validator before every `helm upgrade`:

```bash
python3 tests/validate_jenkins_chart.py
```

The validator checks for:

- Removed or deprecated JCasC keys
- Plugin duplicates and malformed entries
- Secret interpolation references that do not resolve

---

## Troubleshooting

| Symptom                                                                           | Cause                                                                                                       | Fix                                                              |
| --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `config-reload` sidecar: `ECONNREFUSED 10.43.0.1:443`                             | k3s DNAT rewrites ClusterIP to `node:6443` before the NetworkPolicy `FORWARD` chain; port `6443` was missing | Added port `6443` to egress in `network-policy.yaml`             |
| `AggregatePluginPrerequisitesNotMetException`                                     | `audit-trail` / `job-restrictions` had unresolvable transitive deps in 2.555.1                              | Removed both plugins from `installPlugins`                       |
| `ConfigurationAsCodeBootFailure: 'agentProtocols' is deprecated`                  | Key removed from the Jenkins 2.555.1 JCasC model                                                            | Removed `agentProtocols` from `jcasc/jenkins.yaml`               |
| `ConfigurationAsCodeBootFailure: 'fingerprints' invalid`                          | Key removed from the Jenkins 2.555.1 JCasC model                                                            | Removed `fingerprints` block from `jcasc/jenkins.yaml`           |
| `globalMatrix permissions WARNING` (future fatal)                                 | `matrix-auth` 3.x uses `entries:` instead of `permissions:`                                                 | Migrated `security.yaml` to `entries:` format                    |

---

## Day-2 Operations

### Update a plugin version

Change the version in `values.yaml` under `installPlugins`, then run `helm upgrade`. Because `overwritePlugins: true`, the new jar is fetched on the next pod start.

### Rotate secrets

Update the value in Vault. ESO syncs within the `refreshInterval` (`1h`). Jenkins picks up new values on the next JCasC reload or pod restart.

### Add a JCasC configuration

Drop a new `*.yaml` file into `jcasc/`. The `configmap-jcasc.yaml` template picks up all matching files automatically. Run `helm upgrade` to apply.

### Access the UI

Browse to `http://jenkins.proxmox.local`. DNS must resolve to the Traefik VIP. Admin credentials live in Vault at `kv/jenkins/admin`.

### Upgrade the Jenkins version

1. Update the dependency version in `Chart.yaml`.
2. Review the JCasC changelog for removed attributes.
3. Run `python3 tests/validate_jenkins_chart.py`.
4. Run `helm dependency update && helm upgrade`.

---

## Security Notes

- **Docker socket** (`/var/run/docker.sock`) on agents grants effective root on the host node. Acceptable for an internal cluster; **do not** expose the agent namespace externally.
- **Anonymous read** is enabled (`Overall/Read`, `Job/Read`, `View/Read`). Disable when pipelines no longer require public visibility.
- **No TLS on Ingress** — the deployment is on an internal-only network. Enable through `cert-manager` and `controller.ingress.tls` when needed.
- **AppRole `secret-id`** should be rotated regularly:

  ```bash
  vault write -f auth/approle/role/jenkins/secret-id
  ```

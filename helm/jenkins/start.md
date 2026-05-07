# Jenkins As Code

Wrapper Helm chart que entrega o Jenkins na plataforma Proxmox totalmente
declarativo: plugins fixados, configuracao via JCasC, agentes Kubernetes
efemeros, integracao com HashiCorp Vault e injeccao de credenciais via
External Secrets Operator (ESO).

Pensado para ser instalado pelo ArgoCD apontando para `helm/jenkins`.

---

## 1. Estrutura de ficheiros

```
helm/jenkins/
├── Chart.yaml                                    # Wrapper que depende de jenkins/jenkins 5.9.18
├── values.yaml                                   # Valores JCasC, plugins, ingress, agentes, ESO
├── start.md                                      # Este guia
└── templates/
    ├── external-secret-admin.yaml                # Materializa Secret jenkins-admin-secret
    ├── external-secret-git.yaml                  # Materializa Secret jenkins-git-credentials
    └── external-secret-vault-approle.yaml        # Materializa Secret jenkins-vault-approle
```

O que cada ficheiro faz:

- **Chart.yaml**: Declara a dependencia do chart upstream `jenkins` (alias
  `jenkins`) na versao 5.9.18 do repo `https://charts.jenkins.io`. O alias
  garante que tudo o que escrevermos sob `jenkins:` em `values.yaml` chega
  ao chart upstream.
- **values.yaml**: Configuracao completa. Inclui:
  - `controller.installPlugins`: lista pinada de plugins (Configuration as
    Code, Kubernetes, Job DSL, HashiCorp Vault, Credentials, Git, Workflow
    Aggregator, Pipeline Stage View, Matrix Auth, Role Strategy);
  - `controller.JCasC.configScripts`: blocos JCasC (welcome message,
    security realm + matrix auth, credenciais usernamePassword/AppRole,
    configuracao do plugin Vault, seed job de Job DSL);
  - `controller.initScripts.00-hardening`: script Groovy renderizado como
    `init00-hardening.groovy` e executado no boot do controller (desativa CLI remoting, quiet period a 0,
    desativa OldDataMonitor, forca CSRF, regula remoting agente <-> controller);
  - `persistence`: PVC de 10Gi para `${JENKINS_HOME}` usando
    `storageClass: longhorn`;
  - `controller.ingress`: Ingress Traefik para `jenkins.proxmox.local`
    (TLS desligado para acesso interno);
  - `agent`: agentes JNLP em pods Kubernetes no namespace `jenkins` com
    `containerCap: 10` e um `podTemplate` default que ja inclui um
    container `kaniko` para builds de imagens;
  - `externalSecrets`: toggle e paths Vault consumidos pelos templates
    locais.
- **templates/external-secret-admin.yaml**: Cria o `Secret`
  `jenkins-admin-secret` com chaves `jenkins-admin-user` e
  `jenkins-admin-password`, exatamente o formato que o chart upstream
  espera quando `controller.existingSecret` esta definido.
- **templates/external-secret-git.yaml**: Cria o `Secret`
  `jenkins-git-credentials` com `git-username`/`git-password` consumidos
  pelo bloco JCasC `credentials`.
- **templates/external-secret-vault-approle.yaml**: Cria o `Secret`
  `jenkins-vault-approle` com `vault-role-id`/`vault-secret-id` para o
  credential AppRole do plugin Vault.

Todos os ExternalSecrets apontam para a `ClusterSecretStore` chamada
`vault` (criada pelo wrapper `helm/external-secrets`) e ficam protegidos
por `{{ if .Values.externalSecrets.enabled }}`.

---

## 2. Bootstrap

Pre-requisitos no cluster:

- `external-secrets` ja instalado (wrapper `helm/external-secrets`),
  com `ClusterSecretStore/vault` Ready.
- Vault configurado com:
  - KV v2 montado em `kv/`;
  - Policy + role Kubernetes `jenkins` (ver seccao Vault);
  - Caminhos `kv/jenkins/admin`, `kv/jenkins/git`,
    `kv/jenkins/vault-approle` populados.
- Ingress controller Traefik a responder.
- StorageClass `longhorn` disponivel para o PVC de 10Gi.

Comandos (a partir da raiz do repo):

```bash
# 1. Adicionar/atualizar o sub-chart
helm dependency update helm/jenkins

# 2. Instalar/atualizar a release
helm upgrade --install jenkins helm/jenkins \
  --namespace jenkins \
  --create-namespace
```

Se a entrega for via ArgoCD, basta apontar a `Application` para o caminho
`helm/jenkins` e usar `syncPolicy.automated` com `selfHeal: true`.

---

## 3. Validacao

```bash
# Render local sem aplicar nada
helm template jenkins helm/jenkins --namespace jenkins | less

# Estado dos pods
kubectl -n jenkins get pods

# ExternalSecrets reconciliados
kubectl -n jenkins get externalsecret
kubectl -n jenkins get secret jenkins-admin-secret jenkins-git-credentials jenkins-vault-approle

# Logs do controller (deteccao de erros JCasC e initScripts)
kubectl -n jenkins logs deploy/jenkins -c jenkins | grep -E "JCasC|init|ERROR" -i

# UI
curl -I http://jenkins.proxmox.local
```

Erros comuns:

- `Configuration-as-code` falha ao arrancar -> abrir em
  `Manage Jenkins -> Configuration as Code -> View Configuration` e
  comparar com `controller.JCasC.configScripts`.
- Plugins incompativeis -> ajustar versoes em `installPlugins` e voltar a
  correr `helm upgrade`.

---

## 4. Vault

Estrutura esperada (KV v2):

```
kv/jenkins/admin               username=<jenkins-admin-user>
                               password=<jenkins-admin-password>

kv/jenkins/git                 username=<git-user>
                               password=<git-token-ou-password>

kv/jenkins/vault-approle       role-id=<approle-role-id>
                               secret-id=<approle-secret-id>
```

Policy minima a aplicar no Vault (exemplo):

```hcl
# policies/jenkins.hcl
path "kv/data/jenkins/*" {
  capabilities = ["read"]
}
path "kv/metadata/jenkins/*" {
  capabilities = ["read", "list"]
}
```

```bash
vault policy write jenkins policies/jenkins.hcl

vault write auth/kubernetes/role/jenkins \
  bound_service_account_names=jenkins \
  bound_service_account_namespaces=jenkins \
  policies=jenkins \
  ttl=1h
```

Para o plugin HashiCorp Vault dentro do Jenkins (alem do ESO), o
`values.yaml` configura o endpoint `http://vault.proxmox.local`, KV v2 e o
credential `vault-approle-placeholder` declarado em JCasC. Popula
`kv/jenkins/vault-approle` com `role-id`/`secret-id` para o controller
conseguir consultar Vault em pipelines.

---

## 5. DNS / Ingress

- Hostname: `jenkins.proxmox.local`
- IngressClass: `traefik`
- TLS: desligado (rede interna). Para ativar TLS basta editar
  `controller.ingress.tls` em `values.yaml` apontando para um Secret
  emitido pelo cert-manager.

Alternativa nativa Traefik (CRDs `IngressRoute`) caso prefiras nao usar
`Ingress` standard:

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: jenkins
  namespace: jenkins
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`jenkins.proxmox.local`)
      kind: Rule
      services:
        - name: jenkins
          port: 8080
```

Garantir que o registo DNS (PiHole / Unbound / coredns custom) resolve
`jenkins.proxmox.local` para o VIP do Traefik.

---

## 6. Proximos passos

- **Seed jobs**: Substituir o repo placeholder
  `https://git.proxmox.local/platform/jenkins-jobs.git` pelo repo real de
  Job DSL e versionar pipelines. O seed job ja faz `removedJobAction:
  DELETE`, portanto o repo Git e a fonte da verdade.
- **Pipeline libraries**: Adicionar uma `Global Pipeline Library` em JCasC
  (`unclassified.globalLibraries.libraries`) apontando para o repo de
  shared libraries; usar `git-credentials` para autenticacao.
- **RBAC fino**: Migrar de `globalMatrix` para Role Strategy quando
  existirem mais utilizadores; integrar com Keycloak via OIDC plugin.
- **Backup**: Snapshot regular do PVC `${JENKINS_HOME}` (Longhorn
  RecurringJob) e backup logico via `thinBackup` plugin para um bucket
  S3-compatible.
- **Observabilidade**: Expor `Prometheus` plugin e adicionar
  `ServiceMonitor` para a stack `kube-prometheus-stack` ja existente.
- **Hardening adicional**: Ativar TLS no Ingress, restringir
  `anonymous read` quando os pipelines publicos deixarem de ser
  necessarios, rodar `secret-id` do AppRole regularmente.

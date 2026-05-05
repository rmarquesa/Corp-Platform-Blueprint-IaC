"""
Architecture diagram generator for the Proxmox homelab.

Requirements:
    pip install diagrams

Output:
    docs/architecture.png

Run:
    cd docs && python generate_diagram.py
"""

from diagrams import Diagram, Cluster, Edge
from diagrams.onprem.network import Traefik
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.container import Docker
from diagrams.onprem.security import Vault
from diagrams.onprem.gitops import ArgoCD
from diagrams.onprem.logging import Loki
from diagrams.onprem.compute import Server
from diagrams.k8s.compute import Deployment, StatefulSet, DaemonSet
from diagrams.k8s.network import Service
from diagrams.k8s.storage import StorageClass, PersistentVolumeClaim as PVC
from diagrams.saas.identity import Auth0          # Keycloak placeholder
from diagrams.saas.cdn import Cloudflare
from diagrams.generic.network import VPN, Firewall
from diagrams.generic.compute import Rack
from diagrams.generic.storage import Storage

graph_attr = {
    "fontsize": "14",
    "bgcolor": "white",
    "pad": "0.5",
    "splines": "ortho",
    "nodesep": "0.60",
    "ranksep": "0.75",
    "fontname": "Helvetica Neue",
}

node_attr = {
    "fontsize": "11",
    "fontname": "Helvetica Neue",
}

with Diagram(
    "Proxmox Homelab — l3softwares.com",
    filename="architecture",
    outformat="png",
    show=False,
    direction="TB",
    graph_attr=graph_attr,
    node_attr=node_attr,
):
    # ── PUBLIC EDGE ──────────────────────────────────────────────────────────
    with Cluster("Public Edge"):
        cf = Cloudflare("Cloudflare\nDNS + TLS")
        ts = VPN("Tailscale VPN\n10.10.0.0/24")

    # ── PROXMOX HOST ─────────────────────────────────────────────────────────
    with Cluster("Proxmox VE  —  192.168.1.60\nSDN: privnet  10.10.0.0/24"):

        # ── k3s CLUSTER ──────────────────────────────────────────────────────
        with Cluster("k3s HA Cluster"):

            # Control plane
            with Cluster("Control Plane  ×3\n10.10.0.10 – 10.10.0.12\n2vCPU / 4GB"):
                masters = [
                    Server("master-1\n10.10.0.10"),
                    Server("master-2\n10.10.0.11"),
                    Server("master-3\n10.10.0.12"),
                ]

            # Infra workers — cluster tooling
            with Cluster("Infra Workers  ×3  (workload=infra:NoSchedule)\n10.10.0.13 – 10.10.0.15  |  4vCPU / 6GB  |  Longhorn storage"):

                with Cluster("Ingress & Routing"):
                    traefik = Traefik("Traefik v3\nGateway API")
                    cloudflared = Service("cloudflared\ntunnel")

                with Cluster("GitOps"):
                    argocd = ArgoCD("ArgoCD HA\n2 replicas")

                with Cluster("Identity"):
                    keycloak = Auth0("Keycloak\nSSO")

                with Cluster("Observability"):
                    prometheus = Prometheus("Prometheus\n30d retention")
                    grafana = Grafana("Grafana")
                    loki = Loki("Loki\nlog aggregation")
                    tempo = Service("Tempo\ntracing")

                with Cluster("Storage"):
                    longhorn = StorageClass("Longhorn\nreplica=2")
                    longhorn_pvcs = PVC("PVCs\n(Prometheus, Grafana\nLoki, Redis…)")

                with Cluster("Data Layer"):
                    pgbouncer = Service("PgBouncer\ntransaction mode")
                    redis = StatefulSet("Redis HA\nSentinel quorum=2")

            # App workers
            with Cluster("App Workers  ×2  (workload=app)\n10.10.0.16 – 10.10.0.17  |  2vCPU / 4GB"):
                app_workers = [
                    Server("app-1\n10.10.0.16"),
                    Server("app-2\n10.10.0.17"),
                ]

        # ── EXTERNAL VMs ─────────────────────────────────────────────────────
        with Cluster("PostgreSQL HA\nPatroni + etcd  |  VIP: 10.10.0.21"):
            db_vip = Service("Patroni VIP\n10.10.0.21")
            db1 = PostgreSQL("db-1 primary\n10.10.0.20")
            db2 = PostgreSQL("db-2 replica\n10.10.0.22")
            db_arb = Server("db-arbiter\n10.10.0.23\netcd only")

        with Cluster("Services"):
            harbor = Docker("Harbor\nRegistry\n10.10.0.30")
            vault = Vault("HashiCorp\nVault\n10.10.0.31")

        with Cluster("VPN"):
            ts_lxc = VPN("Tailscale LXC\n10.10.0.40\nsubnet router")

    # ── CONNECTIONS ───────────────────────────────────────────────────────────

    # Internet → Cloudflare → cloudflared → Traefik
    cf >> Edge(label="HTTPS tunnel", style="dashed", color="orange") >> cloudflared
    cloudflared >> Edge(label="HTTP") >> traefik

    # Tailscale VPN path (private)
    ts >> Edge(label="WireGuard", style="dashed", color="green") >> ts_lxc

    # Traefik routes
    traefik >> Edge(color="blue") >> argocd
    traefik >> Edge(color="blue") >> keycloak
    traefik >> Edge(color="blue") >> grafana

    # ArgoCD manages everything (GitOps)
    argocd >> Edge(label="GitOps sync", style="dashed", color="gray") >> traefik
    argocd >> Edge(style="dashed", color="gray") >> keycloak
    argocd >> Edge(style="dashed", color="gray") >> prometheus

    # Observability pipeline
    prometheus >> grafana
    loki >> grafana
    tempo >> grafana

    # Storage
    longhorn >> longhorn_pvcs

    # DB connections
    pgbouncer >> Edge(label="5432") >> db_vip
    keycloak >> Edge(label="5432") >> pgbouncer
    db_vip >> db1
    db_vip >> db2
    db1 >> Edge(label="etcd", style="dashed") >> db_arb
    db2 >> Edge(label="etcd", style="dashed") >> db_arb

    # kube-vip HA (masters)
    masters[0] >> Edge(style="dashed", color="purple") >> masters[1]
    masters[1] >> Edge(style="dashed", color="purple") >> masters[2]

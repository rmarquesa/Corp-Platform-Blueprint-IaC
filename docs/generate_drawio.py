#!/usr/bin/env python3
"""Generate a draw.io XML architecture diagram for the Proxmox platform.

Architecture (updated):
  - Proxmox VE host (192.168.1.60) with SDN vnet 10.10.0.0/24
  - PostgreSQL HA: Patroni + etcd, 3 full nodes, DNS failover via CoreDNS etcd plugin
  - k3s HA cluster: 3 masters (kube-vip), 3 infra workers, 2 app workers
  - Infrastructure: CoreDNS, HashiCorp Vault, Tailscale LXC, Harbor
  - k8s workloads: Traefik, ArgoCD, Keycloak, Observability stack, pgBouncer, Redis, Longhorn

Run:
    cd docs && python generate_drawio.py
Output:
    docs/architecture.drawio
"""

from __future__ import annotations
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional


# ── Colour palette ────────────────────────────────────────────────────────────
C = {
    # Edge colours
    "e_traffic": "#0d9488",   # teal  — HTTP traffic
    "e_tunnel":  "#ea580c",   # orange — cloudflare tunnel
    "e_vpn":     "#2563eb",   # blue  — WireGuard
    "e_db":      "#7c3aed",   # violet — DB connections
    "e_repl_s":  "#dc2626",   # red   — sync replication
    "e_repl_a":  "#16a34a",   # green — async replication
    "e_dns":     "#0284c7",   # sky   — DNS / etcd
    "e_oidc":    "#db2777",   # pink  — OIDC
    "e_gitops":  "#059669",   # emerald — GitOps sync
    "e_obs":     "#d97706",   # amber — observability pipeline
    "e_secret":  "#9333ea",   # purple — secrets

    # Zone headers + borders
    "pub_bg": "#F8FAFC", "pub_bd": "#94A3B8",
    "pmx_bg": "#1E293B", "pmx_bd": "#0F172A", "pmx_fg": "#F1F5F9",
    "inf_bg": "#EFF6FF", "inf_bd": "#3B82F6", "inf_fg": "#1E3A8A",
    "hbr_bg": "#FAF5FF", "hbr_bd": "#A855F7", "hbr_fg": "#4C1D95",
    "pg_bg":  "#FFF7ED", "pg_bd":  "#F97316", "pg_fg":  "#7C2D12",
    "k8s_bg": "#F0FDF4", "k8s_bd": "#22C55E", "k8s_fg": "#14532D",
    "cp_bg":  "#FAF5FF", "cp_bd":  "#A855F7", "cp_fg":  "#4C1D95",
    "iw_bg":  "#F0F9FF", "iw_bd":  "#0EA5E9", "iw_fg":  "#0C4A6E",
    "obs_bg": "#FFFBEB", "obs_bd": "#F59E0B", "obs_fg": "#78350F",
    "dat_bg": "#F5F3FF", "dat_bd": "#8B5CF6", "dat_fg": "#3B0764",
    "aw_bg":  "#FFF1F2", "aw_bd":  "#F43F5E", "aw_fg":  "#881337",

    # Node fills / borders
    "n_blue":   "#DBEAFE", "b_blue":   "#2563EB",
    "n_orange": "#FFEDD5", "b_orange": "#EA580C",
    "n_amber":  "#FEF3C7", "b_amber":  "#D97706",
    "n_green":  "#DCFCE7", "b_green":  "#15803D",
    "n_purple": "#EDE9FE", "b_purple": "#7C3AED",
    "n_sky":    "#E0F2FE", "b_sky":    "#0284C7",
    "n_rose":   "#FFE4E6", "b_rose":   "#E11D48",
    "n_teal":   "#CCFBF1", "b_teal":   "#0D9488",
    "n_slate":  "#F1F5F9", "b_slate":  "#64748B",
    "n_red":    "#FEE2E2", "b_red":    "#DC2626",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def lbl(title: str, sub: str = "", icon: str = "") -> str:
    """Build an HTML draw.io label."""
    out = []
    if icon:
        out.append(f'<b style="font-size:18px;">{icon}</b><br/>')
    out.append(f'<b style="font-size:10px;">{title}</b>')
    if sub:
        out.append(f'<br/><font style="font-size:8px;color:#6B7280;">{sub}</font>')
    return "".join(out)


def edge_style(color: str, dashed: bool = False, thick: bool = False) -> str:
    dash = "dashed=1;dashPattern=8 4;" if dashed else ""
    w    = "strokeWidth=2.5;" if thick else "strokeWidth=1.5;"
    return (
        f"edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;"
        f"jettySize=auto;exitX=0.5;exitY=1;exitDx=0;exitDy=0;"
        f"entryX=0.5;entryY=0;entryDx=0;entryDy=0;html=1;"
        f"{dash}{w}strokeColor={color};fillColor=none;"
    )


def zone_style(bg: str, bd: str, fg: str = "#1a1a1a", start: int = 30) -> str:
    return (
        f"swimlane;startSize={start};fillColor={bg};strokeColor={bd};"
        f"fontColor={fg};fontStyle=1;fontSize=11;rounded=1;arcSize=3;"
        f"whiteSpace=wrap;html=1;shadow=0;"
    )


def node_style(bg: str, bd: str, bold: bool = False) -> str:
    fs = "fontStyle=1;" if bold else ""
    return (
        f"rounded=1;whiteSpace=wrap;html=1;fillColor={bg};strokeColor={bd};"
        f"fontSize=10;{fs}shadow=0;arcSize=8;"
    )


def badge_style(bg: str, bd: str) -> str:
    return (
        f"rounded=1;whiteSpace=wrap;html=1;fillColor={bg};strokeColor={bd};"
        f"fontSize=9;fontStyle=1;shadow=0;arcSize=50;"
    )


# ── Builder ───────────────────────────────────────────────────────────────────

class Builder:
    def __init__(self):
        self._cells: list[dict] = []
        self._eid = 200  # edge IDs start at 200

    def _add(self, **kw):
        self._cells.append(kw)

    def zone(self, id: str, value: str, parent: str = "1",
             x: float = 0, y: float = 0, w: float = 400, h: float = 300,
             style: str = "") -> str:
        self._add(id=id, value=value, style=style, parent=parent,
                  vertex=True, x=x, y=y, w=w, h=h)
        return id

    def node(self, id: str, value: str, parent: str = "1",
             x: float = 0, y: float = 0, w: float = 160, h: float = 70,
             style: str = "") -> str:
        self._add(id=id, value=value, style=style, parent=parent,
                  vertex=True, x=x, y=y, w=w, h=h)
        return id

    def edge(self, src: str, tgt: str, label: str = "",
             color: str = "#555", dashed: bool = False, thick: bool = False) -> None:
        self._eid += 1
        lbl_val = (
            f'<font style="font-size:8px;background:#ffffffcc;padding:1px 3px;'
            f'border-radius:2px;color:{color};">{label}</font>'
            if label else ""
        )
        self._add(
            id=f"e{self._eid}", value=lbl_val,
            style=edge_style(color, dashed, thick),
            parent="1", edge=True, source=src, target=tgt,
        )

    def to_xml(self) -> str:
        mxfile = ET.Element("mxfile")
        mxfile.set("host", "app.diagrams.net")
        mxfile.set("version", "24.5.0")

        diag = ET.SubElement(mxfile, "diagram")
        diag.set("name", "Proxmox Platform Architecture")
        diag.set("id", "proxmox-platform-v2")

        model = ET.SubElement(diag, "mxGraphModel")
        for k, v in {
            "dx": "1422", "dy": "762", "grid": "0", "gridSize": "10",
            "guides": "1", "tooltips": "1", "connect": "1", "arrows": "1",
            "fold": "1", "page": "1", "pageScale": "1",
            "pageWidth": "2400", "pageHeight": "1600",
            "math": "0", "shadow": "0",
        }.items():
            model.set(k, v)

        root = ET.SubElement(model, "root")
        c0 = ET.SubElement(root, "mxCell"); c0.set("id", "0")
        c1 = ET.SubElement(root, "mxCell"); c1.set("id", "1"); c1.set("parent", "0")

        for c in self._cells:
            mc = ET.SubElement(root, "mxCell")
            mc.set("id",     str(c["id"]))
            mc.set("value",  str(c["value"]))
            mc.set("style",  str(c["style"]))
            mc.set("parent", str(c["parent"]))
            if c.get("vertex"):
                mc.set("vertex", "1")
            if c.get("edge"):
                mc.set("edge",   "1")
                mc.set("source", str(c["source"]))
                mc.set("target", str(c["target"]))
            geo = ET.SubElement(mc, "mxGeometry")
            if not c.get("edge"):
                geo.set("x", str(c["x"]))
                geo.set("y", str(c["y"]))
                geo.set("width",  str(c["w"]))
                geo.set("height", str(c["h"]))
            else:
                geo.set("relative", "1")
            geo.set("as", "mxGeometry")

        # Pretty-print via manual indent (no minidom dep quirks)
        ET.indent(mxfile, space="  ")
        return ET.tostring(mxfile, encoding="unicode", xml_declaration=False)


# ── Diagram definition ────────────────────────────────────────────────────────

def build() -> str:
    b = Builder()

    # ═══════════════════════════════════════════════════════════════════════════
    # PUBLIC EDGE
    # ═══════════════════════════════════════════════════════════════════════════
    pub = b.zone("pub", "☁  Public Edge",
                 x=30, y=30, w=2160, h=140,
                 style=zone_style(C["pub_bg"], C["pub_bd"], "#374151"))

    b.node("cf",   lbl("Cloudflare", "DNS · TLS termination · WAF", "🌐"),
           parent=pub, x=60, y=40, w=220, h=70,
           style=node_style(C["n_orange"], C["b_orange"]))

    b.node("ts_e", lbl("Tailscale VPN", "Subnet router · WireGuard", "🔒"),
           parent=pub, x=320, y=40, w=220, h=70,
           style=node_style(C["n_sky"], C["b_sky"]))

    # ═══════════════════════════════════════════════════════════════════════════
    # PROXMOX HOST
    # ═══════════════════════════════════════════════════════════════════════════
    pmx = b.zone(
        "pmx",
        "🖥  Proxmox VE  —  192.168.1.60  |  64 GB RAM  |  SDN vnet  10.10.0.0/24",
        x=30, y=190, w=2160, h=1220,
        style=zone_style(C["pmx_bg"], C["pmx_bd"], C["pmx_fg"], start=35),
    )

    # ── Infrastructure ────────────────────────────────────────────────────────
    inf = b.zone("inf", "⚙  Infrastructure Services",
                 parent=pmx, x=20, y=45, w=310, h=390,
                 style=zone_style(C["inf_bg"], C["inf_bd"], C["inf_fg"]))

    b.node("dns",   lbl("CoreDNS", "10.10.0.5 · 512 MB", "🔍"),
           parent=inf, x=20, y=40, w=270, h=75,
           style=node_style(C["n_blue"], C["b_blue"]))

    b.node("vault", lbl("HashiCorp Vault", "10.10.0.31 · 2 GB", "🔐"),
           parent=inf, x=20, y=135, w=270, h=75,
           style=node_style(C["n_purple"], C["b_purple"]))

    b.node("ts_l",  lbl("Tailscale LXC", "10.10.0.40 · subnet router", "🌐"),
           parent=inf, x=20, y=230, w=270, h=75,
           style=node_style(C["n_sky"], C["b_sky"]))

    # ── Harbor ────────────────────────────────────────────────────────────────
    hbr_z = b.zone("hbr_z", "⚓  Container Registry",
                   parent=pmx, x=20, y=455, w=310, h=140,
                   style=zone_style(C["hbr_bg"], C["hbr_bd"], C["hbr_fg"]))

    b.node("harbor", lbl("Harbor", "10.10.0.30 · 8 GB · Docker registry", "⚓"),
           parent=hbr_z, x=20, y=40, w=270, h=70,
           style=node_style(C["n_purple"], C["b_purple"]))

    # ── PostgreSQL HA ─────────────────────────────────────────────────────────
    pg = b.zone(
        "pg",
        "🐘  PostgreSQL HA  —  Patroni + etcd  |  Sync replication  |  DNS failover",
        parent=pmx, x=350, y=45, w=570, h=550,
        style=zone_style(C["pg_bg"], C["pg_bd"], C["pg_fg"]),
    )

    # etcd cluster badge
    b.node("etcd_badge",
           '<b style="font-size:9px;">⚡ etcd Raft cluster — all 3 nodes — quorum = 2 / 3</b>',
           parent=pg, x=20, y=40, w=530, h=35,
           style=badge_style("#FED7AA", "#C2410C"))

    # db nodes
    b.node("db1", lbl("db-1", "10.10.0.20 · 4 GB · 50 GB", "🐘") +
           '<br/><b style="font-size:9px;color:#C2410C;">● Leader</b>',
           parent=pg, x=20, y=90, w=160, h=115,
           style=node_style(C["n_orange"], "#C2410C"))

    b.node("db2", lbl("db-2", "10.10.0.22 · 4 GB · 50 GB", "🐘") +
           '<br/><b style="font-size:9px;color:#B45309;">⟳ Sync Replica  lag=0</b>',
           parent=pg, x=195, y=90, w=160, h=115,
           style=node_style(C["n_amber"], C["b_amber"]))

    b.node("db3", lbl("db-3", "10.10.0.24 · 4 GB · 50 GB", "🐘") +
           '<br/><b style="font-size:9px;color:#15803D;">~ Async DR  nofailover</b>',
           parent=pg, x=370, y=90, w=160, h=115,
           style=node_style(C["n_green"], C["b_green"]))

    # DNS failover endpoint
    b.node("dns_ep",
           '<b style="font-size:10px;">🔀 postgres.proxmox.local</b>'
           '<br/><font style="font-size:8px;color:#1D4ED8;">'
           'CoreDNS etcd plugin · TTL 5 s · Patroni on_role_change callback</font>',
           parent=pg, x=20, y=225, w=530, h=65,
           style=badge_style("#BFDBFE", "#1D4ED8"))

    # pgBouncer note
    b.node("pgb_note",
           '<font style="font-size:8px;">🔀 pgBouncer · transaction pool · '
           'auth_query = pgbouncer.get_auth()</font>',
           parent=pg, x=20, y=305, w=530, h=40,
           style=badge_style(C["n_teal"], C["b_teal"]))

    # Replication mode note
    b.node("repl_note",
           '<font style="font-size:8px;">'
           'synchronous_mode: true · synchronous_node_count: 1<br/>'
           'db-1 ↔ db-2  sync (RPO = 0)  ·  db-3  async (nosync: true)</font>',
           parent=pg, x=20, y=360, w=530, h=55,
           style=badge_style("#FEF9C3", "#CA8A04"))

    # ── k3s Cluster ───────────────────────────────────────────────────────────
    k8s = b.zone(
        "k8s",
        "☸  k3s HA Cluster  —  kube-vip · VIP: 10.10.0.100",
        parent=pmx, x=940, y=45, w=1200, h=1145,
        style=zone_style(C["k8s_bg"], C["k8s_bd"], C["k8s_fg"]),
    )

    # Control Plane
    cp = b.zone("cp", "Control Plane  ×3  —  10.10.0.10 – 12  |  4 GB each",
                parent=k8s, x=20, y=40, w=1160, h=125,
                style=zone_style(C["cp_bg"], C["cp_bd"], C["cp_fg"]))

    b.node("m1", lbl("k8s-master-1", "10.10.0.10"),
           parent=cp, x=20, y=35, w=200, h=65,
           style=node_style(C["n_purple"], C["b_purple"]))
    b.node("m2", lbl("k8s-master-2", "10.10.0.11"),
           parent=cp, x=240, y=35, w=200, h=65,
           style=node_style(C["n_purple"], C["b_purple"]))
    b.node("m3", lbl("k8s-master-3", "10.10.0.12"),
           parent=cp, x=460, y=35, w=200, h=65,
           style=node_style(C["n_purple"], C["b_purple"]))
    b.node("kvip",
           '<b style="font-size:9px;">kube-vip · VRRP · 10.10.0.100</b>',
           parent=cp, x=700, y=35, w=440, h=65,
           style=badge_style(C["n_purple"], C["b_purple"]))

    # Infra Workers
    iw = b.zone(
        "iw",
        "Infra Workers  ×3  —  10.10.0.13 – 15  |  8 GB each  |  taint: workload=infra:NoSchedule",
        parent=k8s, x=20, y=185, w=1160, h=750,
        style=zone_style(C["iw_bg"], C["iw_bd"], C["iw_fg"]),
    )

    b.node("traefik",  lbl("Traefik v3", "Gateway API · ×2", "⚡"),
           parent=iw, x=20, y=40, w=195, h=75,
           style=node_style(C["n_sky"], C["b_sky"]))
    b.node("cloudd",   lbl("cloudflared", "tunnel · ×2", "☁"),
           parent=iw, x=235, y=40, w=195, h=75,
           style=node_style(C["n_orange"], C["b_orange"]))
    b.node("argocd",   lbl("ArgoCD HA", "server×2 · repo×2", "🔄"),
           parent=iw, x=450, y=40, w=195, h=75,
           style=node_style(C["n_sky"], C["b_sky"]))
    b.node("keycloak", lbl("Keycloak 26", "SSO · OIDC · ×1", "🔑"),
           parent=iw, x=665, y=40, w=195, h=75,
           style=node_style(C["n_rose"], C["b_rose"]))
    b.node("longhorn", lbl("Longhorn", "replica=2 · Retain", "💾"),
           parent=iw, x=880, y=40, w=260, h=75,
           style=node_style(C["n_slate"], C["b_slate"]))

    # Observability sub-zone
    obs = b.zone("obs", "📊  Observability Stack",
                 parent=iw, x=20, y=140, w=1120, h=210,
                 style=zone_style(C["obs_bg"], C["obs_bd"], C["obs_fg"]))

    b.node("prom",  lbl("Prometheus", "30 d · 10 Gi", "📈"),
           parent=obs, x=20, y=40, w=210, h=75,
           style=node_style(C["n_amber"], C["b_amber"]))
    b.node("gfn",   lbl("Grafana", "OIDC SSO", "📊"),
           parent=obs, x=250, y=40, w=210, h=75,
           style=node_style(C["n_orange"], C["b_orange"]))
    b.node("loki",  lbl("Loki", "10 Gi logs", "📜"),
           parent=obs, x=480, y=40, w=210, h=75,
           style=node_style(C["n_amber"], C["b_amber"]))
    b.node("tempo", lbl("Tempo", "72 h traces · 10 Gi", "🔭"),
           parent=obs, x=710, y=40, w=210, h=75,
           style=node_style(C["n_amber"], C["b_amber"]))

    # Data layer sub-zone
    dat = b.zone("dat", "💽  Data Layer",
                 parent=iw, x=20, y=375, w=640, h=195,
                 style=zone_style(C["dat_bg"], C["dat_bd"], C["dat_fg"]))

    b.node("pgb",   lbl("pgBouncer ×2", "transaction mode · :5432", "🔀"),
           parent=dat, x=20, y=40, w=280, h=75,
           style=node_style(C["n_teal"], C["b_teal"]))
    b.node("redis", lbl("Redis HA", "master + 2 replicas · Sentinel", "⚡"),
           parent=dat, x=330, y=40, w=280, h=75,
           style=node_style(C["n_rose"], C["b_rose"]))

    # App Workers
    aw = b.zone("aw", "App Workers  ×2  —  10.10.0.16 – 17  |  4 GB each",
                parent=k8s, x=20, y=955, w=1160, h=165,
                style=zone_style(C["aw_bg"], C["aw_bd"], C["aw_fg"]))

    b.node("a1", lbl("k8s-app-1", "10.10.0.16"),
           parent=aw, x=20, y=40, w=200, h=75,
           style=node_style(C["n_rose"], C["b_rose"]))
    b.node("a2", lbl("k8s-app-2", "10.10.0.17"),
           parent=aw, x=240, y=40, w=200, h=75,
           style=node_style(C["n_rose"], C["b_rose"]))

    # ═══════════════════════════════════════════════════════════════════════════
    # EDGES
    # ═══════════════════════════════════════════════════════════════════════════

    # ── Public → cluster ──────────────────────────────────────────────────────
    b.edge("cf",    "cloudd",   "HTTPS tunnel",   C["e_tunnel"], dashed=True, thick=True)
    b.edge("ts_e",  "ts_l",     "WireGuard",      C["e_vpn"],    dashed=True)
    b.edge("cloudd","traefik",  "HTTP",           C["e_traffic"], thick=True)

    # ── Traefik routing ───────────────────────────────────────────────────────
    b.edge("traefik", "argocd",   "", C["e_traffic"])
    b.edge("traefik", "keycloak", "", C["e_traffic"])
    b.edge("traefik", "gfn",      "", C["e_traffic"])
    b.edge("traefik", "longhorn", "", C["e_traffic"])

    # ── OIDC ──────────────────────────────────────────────────────────────────
    b.edge("keycloak", "gfn", "OIDC SSO", C["e_oidc"])

    # ── DB connection chain ───────────────────────────────────────────────────
    b.edge("keycloak", "pgb",    "5432",             C["e_db"], thick=True)
    b.edge("harbor",   "pgb",    "5432",             C["e_db"])
    b.edge("pgb",      "dns_ep", "pool → leader",    C["e_db"], thick=True)

    # ── DNS failover ─────────────────────────────────────────────────────────
    b.edge("dns",    "dns_ep", "etcd plugin · TTL 5 s", C["e_dns"], dashed=True)

    # ── Patroni replication ───────────────────────────────────────────────────
    b.edge("db1", "db2", "sync  RPO=0",  C["e_repl_s"], thick=True)
    b.edge("db2", "db3", "async DR",     C["e_repl_a"], dashed=True)

    # ── Observability pipeline ────────────────────────────────────────────────
    b.edge("prom",  "gfn", "metrics", C["e_obs"])
    b.edge("loki",  "gfn", "logs",    C["e_obs"])
    b.edge("tempo", "gfn", "traces",  C["e_obs"])

    # ── ArgoCD GitOps ─────────────────────────────────────────────────────────
    b.edge("argocd", "traefik",  "sync", C["e_gitops"], dashed=True)
    b.edge("argocd", "keycloak", "sync", C["e_gitops"], dashed=True)

    # ── Vault secrets ─────────────────────────────────────────────────────────
    b.edge("vault", "keycloak", "secrets", C["e_secret"], dashed=True)
    b.edge("vault", "pgb",      "secrets", C["e_secret"], dashed=True)

    return b.to_xml()


if __name__ == "__main__":
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    xml_out = build()
    with open("architecture.drawio", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_out)
    print("✓ Generated: docs/architecture.drawio")
    print("  Open at: https://app.diagrams.net or File → Open in draw.io desktop")

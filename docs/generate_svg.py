#!/usr/bin/env python3
"""Generate a standalone SVG architecture diagram — opens in any browser."""

from __future__ import annotations
import math, os

W, H = 2440, 1630   # canvas

# ── Colour palette ────────────────────────────────────────────────────────────
Z = {                               # zone header bg / border / label colour
    "pub":  ("#E2E8F0", "#94A3B8", "#1E293B"),
    "pmx":  ("#1E293B", "#0F172A", "#F1F5F9"),
    "inf":  ("#DBEAFE", "#3B82F6", "#1E3A8A"),
    "hbr":  ("#EDE9FE", "#8B5CF6", "#3B0764"),
    "pg":   ("#FED7AA", "#F97316", "#7C2D12"),
    "k8s":  ("#BBF7D0", "#16A34A", "#14532D"),
    "cp":   ("#E9D5FF", "#A855F7", "#4C1D95"),
    "iw":   ("#BAE6FD", "#0EA5E9", "#0C4A6E"),
    "obs":  ("#FDE68A", "#F59E0B", "#78350F"),
    "dat":  ("#DDD6FE", "#7C3AED", "#3B0764"),
    "aw":   ("#FECDD3", "#F43F5E", "#881337"),
}
N = {                               # node fill / border
    "blue":   ("#DBEAFE", "#2563EB"),
    "orange": ("#FFEDD5", "#EA580C"),
    "amber":  ("#FEF3C7", "#D97706"),
    "green":  ("#DCFCE7", "#15803D"),
    "purple": ("#EDE9FE", "#7C3AED"),
    "sky":    ("#E0F2FE", "#0284C7"),
    "rose":   ("#FFE4E6", "#E11D48"),
    "teal":   ("#CCFBF1", "#0D9488"),
    "slate":  ("#F1F5F9", "#475569"),
    "red":    ("#FEE2E2", "#DC2626"),
}
EDGE = {
    "traffic": "#0D9488",
    "tunnel":  "#EA580C",
    "vpn":     "#2563EB",
    "db":      "#7C3AED",
    "repl_s":  "#DC2626",
    "repl_a":  "#15803D",
    "dns":     "#0284C7",
    "oidc":    "#DB2777",
    "gitops":  "#059669",
    "obs":     "#D97706",
    "secret":  "#9333EA",
}

# ── SVG builder ───────────────────────────────────────────────────────────────

class SVG:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self._defs: list[str] = []
        self._bg:   list[str] = []   # drawn first (zones)
        self._mid:  list[str] = []   # nodes
        self._top:  list[str] = []   # edges + labels on top
        self._nodes: dict[str, tuple[float,float,float,float]] = {}  # id→(cx,cy,w,h)

    # ── primitives ────────────────────────────────────────────────────────────

    def _rect(self, x, y, w, h, fill, stroke, rx=10, opacity=1.0,
              stroke_width=1.5, dash="") -> str:
        d = f'stroke-dasharray="{dash}"' if dash else ""
        return (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{stroke_width}" opacity="{opacity}" {d}/>'
        )

    def _text(self, x, y, txt, size=11, bold=False, color="#1a1a1a",
              anchor="middle", dy=0) -> str:
        w = "bold" if bold else "normal"
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" dy="{dy}" font-family="SF Pro Display,'
            f'Helvetica Neue,Arial,sans-serif" font-size="{size}" '
            f'font-weight="{w}" fill="{color}" text-anchor="{anchor}">'
            f'{txt}</text>'
        )

    def _line(self, x1, y1, x2, y2, color, width=1.5, dash="") -> str:
        d = f'stroke-dasharray="{dash}"' if dash else ""
        return (
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="{width}" {d}/>'
        )

    # ── compound shapes ───────────────────────────────────────────────────────

    def zone(self, x, y, w, h, key: str, label: str,
             header_h=32, layer="bg") -> tuple[float,float]:
        """Draw a zone rectangle. Returns (content_x, content_y) for children."""
        bg, bd, fg = Z[key]
        tgt = self._bg if layer == "bg" else self._mid
        # shadow
        self._bg.append(
            f'<rect x="{x+4:.1f}" y="{y+4:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="12" fill="#00000018"/>'
        )
        # body
        tgt.append(self._rect(x, y, w, h, bg, bd, rx=12, stroke_width=2))
        # header band
        tgt.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{header_h}" '
            f'rx="12" fill="{bd}22" stroke="none"/>'
        )
        # clipping rect for top corners only
        tgt.append(self._text(x + w/2, y + header_h/2 + 5, label,
                              size=11, bold=True, color=fg))
        return x, y + header_h  # content origin

    def node(self, id: str, cx: float, cy: float, w: float, h: float,
             icon: str, title: str, sub: str, color_key: str) -> None:
        fill, stroke = N[color_key]
        x, y = cx - w/2, cy - h/2
        self._nodes[id] = (cx, cy, w, h)
        # shadow
        self._mid.append(
            f'<rect x="{x+3:.1f}" y="{y+3:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="8" fill="#00000015"/>'
        )
        self._mid.append(self._rect(x, y, w, h, fill, stroke, rx=8, stroke_width=1.8))
        # icon
        if icon:
            self._mid.append(self._text(cx, cy - h/2 + 22, icon, size=18, anchor="middle"))
        # title
        self._mid.append(self._text(cx, cy + (2 if icon else -4), title,
                                     size=10, bold=True, anchor="middle"))
        # subtitle
        if sub:
            self._mid.append(self._text(cx, cy + (17 if icon else 12), sub,
                                         size=8, color="#6B7280", anchor="middle"))

    def badge(self, id: str, x: float, y: float, w: float, h: float,
              text: str, text2: str = "", fill="#F1F5F9", stroke="#CBD5E1") -> None:
        cx, cy = x + w/2, y + h/2
        self._nodes[id] = (cx, cy, w, h)
        self._mid.append(self._rect(x, y, w, h, fill, stroke, rx=20, stroke_width=1.5))
        if text2:
            self._mid.append(self._text(cx, cy - 5, text, size=9, bold=True, anchor="middle"))
            self._mid.append(self._text(cx, cy + 9, text2, size=8, color="#6B7280", anchor="middle"))
        else:
            self._mid.append(self._text(cx, cy + 4, text, size=9, bold=True, anchor="middle"))

    def edge(self, src: str, tgt: str, label: str, color: str,
             dashed=False, thick=False) -> None:
        if src not in self._nodes or tgt not in self._nodes:
            return
        sx, sy, sw, sh = self._nodes[src]
        tx, ty, tw, th = self._nodes[tgt]
        # simple orthogonal routing: exit bottom, enter top (or side if needed)
        # Determine exit/entry points based on relative positions
        dx = tx - sx
        dy = ty - sy
        if abs(dy) > abs(dx) * 0.5:
            # mostly vertical
            if dy > 0:
                x1, y1 = sx, sy + sh/2
                x2, y2 = tx, ty - th/2
            else:
                x1, y1 = sx, sy - sh/2
                x2, y2 = tx, ty + th/2
        else:
            # mostly horizontal
            if dx > 0:
                x1, y1 = sx + sw/2, sy
                x2, y2 = tx - tw/2, ty
            else:
                x1, y1 = sx - sw/2, sy
                x2, y2 = tx + tw/2, ty

        # Mid-point for curve
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2
        # Bezier control points
        cpx1 = x1 + (mx - x1) * 0.5
        cpy1 = y1 + (my - y1) * 0.2
        cpx2 = x2 - (x2 - mx) * 0.5
        cpy2 = y2 - (y2 - my) * 0.2

        w = 2.5 if thick else 1.6
        dash = "8,4" if dashed else ""
        d_attr = (
            f'stroke-dasharray="{dash}"' if dash else ""
        )
        path = (
            f'<path d="M{x1:.1f},{y1:.1f} C{cpx1:.1f},{cpy1:.1f} '
            f'{cpx2:.1f},{cpy2:.1f} {x2:.1f},{y2:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="{w}" {d_attr} '
            f'marker-end="url(#arr_{color[1:]})" opacity="0.85"/>'
        )
        self._top.append(path)

        if label:
            lx, ly = (x1+x2)/2, (y1+y2)/2 - 6
            # label pill
            lw = len(label) * 5.5 + 10
            self._top.append(
                f'<rect x="{lx - lw/2:.1f}" y="{ly - 9:.1f}" '
                f'width="{lw:.1f}" height="16" rx="8" '
                f'fill="white" stroke="{color}" stroke-width="1" opacity="0.92"/>'
            )
            self._top.append(self._text(lx, ly + 3, label, size=8,
                                         color=color, anchor="middle"))

    def _arrowhead(self, color: str) -> str:
        key = color[1:]
        return (
            f'<marker id="arr_{key}" markerWidth="8" markerHeight="6" '
            f'refX="7" refY="3" orient="auto">'
            f'<path d="M0,0 L8,3 L0,6 Z" fill="{color}"/></marker>'
        )

    def render(self) -> str:
        colors = set(EDGE.values())
        arrows = "\n    ".join(self._arrowhead(c) for c in colors)
        defs = f"<defs>\n    {arrows}\n  </defs>"

        layers = "\n  ".join(self._bg + self._mid + self._top)
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">\n'
            f'  {defs}\n'
            f'  <rect width="{self.w}" height="{self.h}" fill="#F8FAFC"/>\n'
            f'  {layers}\n'
            f'</svg>'
        )


# ── Layout ────────────────────────────────────────────────────────────────────

def build() -> str:
    s = SVG(W, H)

    # ── PUBLIC EDGE ───────────────────────────────────────────────────────────
    s.zone(30, 30, 2160, 140, "pub", "☁  Public Edge", header_h=30)
    s.node("cf",   160, 105, 220, 75, "🌐", "Cloudflare", "DNS · TLS · WAF",   "orange")
    s.node("ts_e", 420, 105, 220, 75, "🔒", "Tailscale VPN", "Subnet · WireGuard", "sky")

    # ── PROXMOX HOST ──────────────────────────────────────────────────────────
    s.zone(30, 190, 2160, 1220, "pmx",
           "🖥  Proxmox VE  —  192.168.1.60  |  64 GB RAM  |  SDN vnet 10.10.0.0/24",
           header_h=36)

    # ── Infrastructure ────────────────────────────────────────────────────────
    s.zone(50, 246, 310, 385, "inf", "⚙  Infrastructure", header_h=30, layer="mid")
    s.node("dns",   205, 316, 270, 72, "🔍", "CoreDNS",        "10.10.0.5 · 512 MB",  "blue")
    s.node("vault", 205, 408, 270, 72, "🔐", "HashiCorp Vault", "10.10.0.31 · 2 GB",   "purple")
    s.node("ts_l",  205, 500, 270, 72, "🌐", "Tailscale LXC",  "10.10.0.40 · router",  "sky")

    # ── Harbor ────────────────────────────────────────────────────────────────
    s.zone(50, 650, 310, 140, "hbr", "⚓  Registry", header_h=30, layer="mid")
    s.node("harbor", 205, 717, 270, 70, "⚓", "Harbor",
           "10.10.0.30 · 8 GB", "purple")

    # ── PostgreSQL HA ─────────────────────────────────────────────────────────
    s.zone(380, 246, 570, 565, "pg",
           "🐘  PostgreSQL HA  —  Patroni + etcd  |  DNS failover",
           header_h=32, layer="mid")

    s.badge("etcd_badge", 400, 290, 530, 34,
            "⚡  etcd Raft cluster  —  3 nodes  —  quorum = 2 / 3",
            fill="#FED7AA", stroke="#C2410C")

    s.node("db1", 480, 400, 158, 118, "🐘", "db-1  ●Leader",
           "10.10.0.20 · 4 GB", "orange")
    s.node("db2", 655, 400, 158, 118, "🐘", "db-2  ⟳Sync",
           "10.10.0.22 · 4 GB", "amber")
    s.node("db3", 830, 400, 158, 118, "🐘", "db-3  ~Async DR",
           "10.10.0.24 · nofailover", "green")

    s.badge("dns_ep", 400, 482, 530, 62,
            "🔀  postgres.proxmox.local  →  leader IP (TTL 5 s)",
            "CoreDNS etcd plugin  ·  Patroni on_role_change callback",
            fill="#BFDBFE", stroke="#1D4ED8")

    s.badge("pgb_note", 400, 558, 530, 38,
            "pgBouncer · transaction pool · auth_query = pgbouncer.get_auth()",
            fill="#CCFBF1", stroke="#0D9488")

    s.badge("repl_note", 400, 608, 530, 52,
            "synchronous_mode: true · synchronous_node_count: 1",
            "db-1 ↔ db-2 sync (RPO=0)  ·  db-3 async (nosync: true)",
            fill="#FEF9C3", stroke="#CA8A04")

    # ── k3s Cluster ───────────────────────────────────────────────────────────
    s.zone(970, 246, 1200, 1148, "k8s",
           "☸  k3s HA Cluster  —  kube-vip  10.10.0.100",
           header_h=32, layer="mid")

    # Control Plane
    s.zone(990, 290, 1160, 128, "cp",
           "Control Plane  ×3  —  10.10.0.10–12  |  4 GB",
           header_h=28, layer="mid")
    s.node("m1",   1100, 354, 190, 62, None, "k8s-master-1", "10.10.0.10", "purple")
    s.node("m2",   1310, 354, 190, 62, None, "k8s-master-2", "10.10.0.11", "purple")
    s.node("m3",   1520, 354, 190, 62, None, "k8s-master-3", "10.10.0.12", "purple")
    s.badge("kvip", 1740, 322, 390, 62,
            "kube-vip · VRRP · VIP 10.10.0.100",
            fill="#EDE9FE", stroke="#7C3AED")

    # Infra Workers
    s.zone(990, 436, 1160, 770, "iw",
           "Infra Workers  ×3  —  10.10.0.13–15  |  8 GB  |  taint: workload=infra:NoSchedule",
           header_h=28, layer="mid")

    s.node("traefik",  1092, 510, 185, 74, "⚡", "Traefik v3", "Gateway API · ×2", "sky")
    s.node("cloudd",   1295, 510, 185, 74, "☁", "cloudflared", "tunnel · ×2",     "orange")
    s.node("argocd",   1498, 510, 185, 74, "🔄", "ArgoCD HA",  "server×2 · repo×2","sky")
    s.node("keycloak", 1700, 510, 185, 74, "🔑", "Keycloak 26","SSO · OIDC",        "rose")
    s.node("longhorn", 1930, 510, 230, 74, "💾", "Longhorn",   "replica=2 · Retain","slate")

    # Observability
    s.zone(1010, 602, 1120, 218, "obs", "📊  Observability", header_h=28, layer="mid")
    s.node("prom",  1122, 672, 200, 72, "📈", "Prometheus", "30 d · 10 Gi",     "amber")
    s.node("gfn",   1335, 672, 200, 72, "📊", "Grafana",    "OIDC SSO",          "orange")
    s.node("loki",  1548, 672, 200, 72, "📜", "Loki",       "10 Gi logs",        "amber")
    s.node("tempo", 1762, 672, 200, 72, "🔭", "Tempo",      "72 h · 10 Gi",      "amber")

    # Data layer
    s.zone(1010, 840, 640, 198, "dat", "💽  Data Layer", header_h=28, layer="mid")
    s.node("pgb",   1170, 910, 280, 74, "🔀", "pgBouncer ×2", ":5432 · tx pool", "teal")
    s.node("redis", 1490, 910, 280, 74, "⚡", "Redis HA",     "master+2 · Sentinel","rose")

    # App Workers
    s.zone(990, 1060, 1160, 155, "aw",
           "App Workers  ×2  —  10.10.0.16–17  |  4 GB",
           header_h=28, layer="mid")
    s.node("a1", 1100, 1143, 200, 70, None, "k8s-app-1", "10.10.0.16", "rose")
    s.node("a2", 1310, 1143, 200, 70, None, "k8s-app-2", "10.10.0.17", "rose")

    # ── EDGES ─────────────────────────────────────────────────────────────────

    # Public edge
    s.edge("cf",     "cloudd",   "HTTPS tunnel", EDGE["tunnel"], dashed=True, thick=True)
    s.edge("ts_e",   "ts_l",     "WireGuard",    EDGE["vpn"],    dashed=True)
    s.edge("cloudd", "traefik",  "HTTP",         EDGE["traffic"], thick=True)

    # Traefik routing
    s.edge("traefik", "argocd",   "", EDGE["traffic"])
    s.edge("traefik", "keycloak", "", EDGE["traffic"])
    s.edge("traefik", "gfn",      "", EDGE["traffic"])
    s.edge("traefik", "longhorn", "", EDGE["traffic"])

    # OIDC
    s.edge("keycloak", "gfn", "OIDC SSO", EDGE["oidc"])

    # DB chain
    s.edge("keycloak", "pgb",    "5432",          EDGE["db"], thick=True)
    s.edge("harbor",   "pgb",    "5432",          EDGE["db"])
    s.edge("pgb",      "dns_ep", "pool → leader", EDGE["db"], thick=True)

    # DNS failover
    s.edge("dns", "dns_ep", "etcd plugin · TTL 5s", EDGE["dns"], dashed=True)

    # Replication
    s.edge("db1", "db2", "sync RPO=0", EDGE["repl_s"], thick=True)
    s.edge("db2", "db3", "async DR",   EDGE["repl_a"], dashed=True)

    # Observability pipeline
    s.edge("prom",  "gfn", "metrics", EDGE["obs"])
    s.edge("loki",  "gfn", "logs",    EDGE["obs"])
    s.edge("tempo", "gfn", "traces",  EDGE["obs"])

    # GitOps
    s.edge("argocd", "traefik",  "sync", EDGE["gitops"], dashed=True)
    s.edge("argocd", "keycloak", "sync", EDGE["gitops"], dashed=True)

    # Vault
    s.edge("vault", "keycloak", "secrets", EDGE["secret"], dashed=True)
    s.edge("vault", "pgb",      "secrets", EDGE["secret"], dashed=True)

    # Legend
    _legend(s)

    return s.render()


def _legend(s: SVG):
    lx, ly, lw = 30, 1490, 230
    s._mid.append(s._rect(lx, ly, lw, 320, "#FFFFFF", "#CBD5E1", rx=10,
                           stroke_width=1.5))
    s._mid.append(s._text(lx + lw/2, ly + 18, "Legend", size=10,
                           bold=True, color="#374151", anchor="middle"))
    items = [
        (EDGE["traffic"], False, "HTTP / service traffic"),
        (EDGE["tunnel"],  True,  "Cloudflare tunnel"),
        (EDGE["db"],      False, "Database connection"),
        (EDGE["repl_s"],  False, "Sync replication (RPO=0)"),
        (EDGE["repl_a"],  True,  "Async replication (DR)"),
        (EDGE["dns"],     True,  "DNS / etcd (TTL 5 s)"),
        (EDGE["oidc"],    False, "OIDC SSO"),
        (EDGE["gitops"],  True,  "GitOps sync (ArgoCD)"),
        (EDGE["secret"],  True,  "Vault secret injection"),
    ]
    for i, (color, dashed, label) in enumerate(items):
        y = ly + 38 + i * 30
        dash = "8,4" if dashed else ""
        s._mid.append(s._line(lx + 14, y, lx + 44, y, color, 2, dash))
        s._mid.append(s._text(lx + 54, y + 4, label, size=9,
                               color="#374151", anchor="start"))


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    svg = build()
    with open("architecture.svg", "w", encoding="utf-8") as f:
        f.write(svg)
    print("✓ Generated: docs/architecture.svg")

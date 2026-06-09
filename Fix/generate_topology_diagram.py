# Membuat diagram statis topologi Cyber Range/Digital Twin.
# Output default: Fix/Graphs/Pics/topologi_cyber_range.(png|pdf).

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch


# Lokasi output mengikuti struktur Fix/Graphs/Pics.
ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = ROOT_DIR / "Graphs" / "Pics"
DEFAULT_BASENAME = "topologi_cyber_range"


# Definisi zona visual: posisi, ukuran, subnet, dan warna latar.
ZONES = [
    {
        "name": "Field Zone",
        "subnet": "10.0.1.0/24",
        "xy": (0.2, 1.0),
        "width": 4.0,
        "height": 2.65,
        "color": "#DCEBFF",
    },
    {
        "name": "Control Zone",
        "subnet": "10.0.2.0/24",
        "xy": (5.0, 1.0),
        "width": 4.0,
        "height": 2.65,
        "color": "#E6F4EA",
    },
    {
        "name": "IT Zone",
        "subnet": "10.0.3.0/24",
        "xy": (9.8, 1.0),
        "width": 3.6,
        "height": 2.65,
        "color": "#F9E6E2",
    },
]


# Definisi node visual: koordinat, label multiline, dan tipe style.
NODES = {
    "h1": {
        "pos": (1.0, 2.75),
        "label": "h1\nField Process\nModbus Server",
        "kind": "host",
    },
    "h2": {
        "pos": (3.05, 2.75),
        "label": "h2\nRTU\nModbus Client",
        "kind": "host",
    },
    "h3": {
        "pos": (6.0, 2.75),
        "label": "h3\nGateway\nModbus + OPC UA",
        "kind": "host",
    },
    "h5": {
        "pos": (8.1, 2.75),
        "label": "h5\nAttacker\nDoS / MITM",
        "kind": "attacker",
    },
    "h4": {
        "pos": (11.55, 2.75),
        "label": "h4\nDigital Twin\nOPC UA Client",
        "kind": "host",
    },
    "s1": {
        "pos": (2.0, 1.75),
        "label": "s1\nField Switch",
        "kind": "switch",
    },
    "s2": {
        "pos": (6.9, 1.75),
        "label": "s2\nControl Switch",
        "kind": "switch",
    },
    "s3": {
        "pos": (11.55, 1.75),
        "label": "s3\nIT Switch",
        "kind": "switch",
    },
    "s4": {
        "pos": (6.75, 0.35),
        "label": "s4\nCore Switch",
        "kind": "switch",
    },
    "r0": {
        "pos": (6.75, 4.55),
        "label": "r0\nRouter / Firewall\nDefault deny",
        "kind": "router",
    },
}


# Link fisik/virtual Mininet yang digambar sebagai garis biasa.
LINKS = [
    ("h1", "s1", "5 Mbps"),
    ("h2", "s1", "5 Mbps"),
    ("h3", "s2", "5 Mbps"),
    ("h5", "s2", "5 Mbps"),
    ("h4", "s3", "5 Mbps"),
    ("s1", "s4", "5 Mbps"),
    ("s2", "s4", "5 Mbps"),
    ("s3", "s4", "5 Mbps"),
    ("r0", "s1", "Field GW\n10.0.1.1"),
    ("r0", "s2", "Control GW\n10.0.2.1"),
    ("r0", "s3", "IT GW\n10.0.3.1"),
]


# Alur komunikasi normal digambar sebagai panah di atas link.
DATA_FLOWS = [
    ("h1", "h2", "Modbus TCP"),
    ("h2", "h3", "Modbus TCP"),
    ("h3", "h4", "OPC UA"),
]


# Style dibedakan agar host, switch, router, dan attacker mudah dikenali.
NODE_STYLES = {
    "host": {"facecolor": "#FFFFFF", "edgecolor": "#315B7D"},
    "switch": {"facecolor": "#F7F7F2", "edgecolor": "#6C6A5D"},
    "router": {"facecolor": "#FFF1C7", "edgecolor": "#8A6D1D"},
    "attacker": {"facecolor": "#FFE1E1", "edgecolor": "#A33A3A"},
}


def draw_zone(ax, zone):
    """Gambar kotak zona jaringan beserta label subnet."""
    x, y = zone["xy"]
    patch = FancyBboxPatch(
        (x, y),
        zone["width"],
        zone["height"],
        boxstyle="round,pad=0.04,rounding_size=0.08",
        linewidth=1.2,
        edgecolor="#667085",
        facecolor=zone["color"],
        alpha=0.72,
        zorder=0,
    )
    ax.add_patch(patch)
    ax.text(
        x + 0.16,
        y + zone["height"] - 0.18,
        f"{zone['name']} ({zone['subnet']})",
        ha="left",
        va="top",
        fontsize=10.5,
        fontweight="bold",
        color="#1F2937",
    )


def draw_node(ax, name, node):
    """Gambar node sebagai rounded box kecil dengan label di tengah."""
    x, y = node["pos"]
    kind = node["kind"]
    width = 1.55 if kind != "router" else 1.85
    height = 0.62 if kind != "router" else 0.72
    style = NODE_STYLES[kind]

    patch = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.04,rounding_size=0.06",
        linewidth=1.4,
        facecolor=style["facecolor"],
        edgecolor=style["edgecolor"],
        zorder=3,
    )
    ax.add_patch(patch)
    ax.text(
        x,
        y,
        node["label"],
        ha="center",
        va="center",
        fontsize=8.5,
        color="#111827",
        zorder=4,
    )


def draw_link(ax, a, b, label="", *, dashed=False, color="#475467", width=1.4, zorder=1):
    """Gambar link antar node; garis putus-putus dipakai untuk jalur MITM opsional."""
    x1, y1 = NODES[a]["pos"]
    x2, y2 = NODES[b]["pos"]
    linestyle = (0, (5, 4)) if dashed else "solid"
    ax.plot([x1, x2], [y1, y2], color=color, linewidth=width, linestyle=linestyle, zorder=zorder)

    if label:
        mx = x1 + (x2 - x1) * 0.5
        my = y1 + (y2 - y1) * 0.5
        ax.text(
            mx,
            my + 0.08,
            label,
            ha="center",
            va="bottom",
            fontsize=7.5,
            color=color,
            bbox={"boxstyle": "round,pad=0.16", "fc": "white", "ec": "none", "alpha": 0.82},
            zorder=2,
        )


def draw_arrow(ax, a, b, label, *, color="#2563EB", curve=0.0):
    """Gambar panah alur data agar protokol antar host terlihat jelas."""
    x1, y1 = NODES[a]["pos"]
    x2, y2 = NODES[b]["pos"]
    ax.annotate(
        "",
        xy=(x2, y2 + curve),
        xytext=(x1, y1 + curve),
        arrowprops={
            "arrowstyle": "-|>",
            "color": color,
            "lw": 1.5,
            "shrinkA": 28,
            "shrinkB": 28,
            "connectionstyle": "arc3,rad=0.08",
        },
        zorder=5,
    )
    mx = x1 + (x2 - x1) * 0.5
    my = y1 + (y2 - y1) * 0.5 + curve + 0.18
    ax.text(
        mx,
        my,
        label,
        ha="center",
        va="center",
        fontsize=8,
        color=color,
        bbox={"boxstyle": "round,pad=0.18", "fc": "white", "ec": color, "alpha": 0.9},
        zorder=6,
    )


def draw_policy_notes(ax):
    """Tambahkan catatan kebijakan firewall r0 dan blok Field-IT."""
    ax.text(
        6.75,
        5.25,
        "Segmentasi r0: Field <-> Control diizinkan, Control <-> IT diizinkan, Field <-> IT diblok",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        color="#344054",
        bbox={"boxstyle": "round,pad=0.28", "fc": "#F8FAFC", "ec": "#CBD5E1"},
    )
    ax.text(
        5.1,
        4.55,
        "BLOCK\nField <-> IT",
        ha="center",
        va="center",
        fontsize=8,
        color="#B42318",
        fontweight="bold",
        bbox={"boxstyle": "round,pad=0.2", "fc": "#FFF5F5", "ec": "#FDA29B"},
    )


def draw_legend(ax):
    """Tambahkan legend link, alur normal, dan jalur MITM."""
    legend_items = [
        Line2D([0], [0], color="#475467", lw=1.5, label="Link Mininet / TCLink"),
        Line2D([0], [0], color="#2563EB", lw=1.5, label="Alur data normal"),
        Line2D([0], [0], color="#B42318", lw=1.5, linestyle=(0, (5, 4)), label="Jalur MITM aktif saat eskalasi"),
    ]
    ax.legend(
        handles=legend_items,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.03),
        ncol=3,
        frameon=False,
        fontsize=8.5,
    )


def build_figure():
    """Rakit seluruh elemen diagram ke satu figure matplotlib."""
    fig, ax = plt.subplots(figsize=(14, 6.2))
    ax.set_xlim(0, 13.8)
    ax.set_ylim(-0.15, 5.6)
    ax.axis("off")

    for zone in ZONES:
        draw_zone(ax, zone)

    for source, target, label in LINKS:
        draw_link(ax, source, target, label)

    draw_link(
        ax,
        "h5",
        "s1",
        "eth1 -> 10.0.1.100\naktif saat MITM",
        dashed=True,
        color="#B42318",
        width=1.5,
        zorder=2,
    )

    for name, node in NODES.items():
        draw_node(ax, name, node)

    for source, target, label in DATA_FLOWS:
        draw_arrow(ax, source, target, label, curve=0.45)

    draw_policy_notes(ax)
    draw_legend(ax)

    fig.suptitle(
        "Topologi Cyber Range Mininet dan Digital Twin",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    return fig


def save_diagram(output_dir: Path, basename: str, formats: list[str]) -> list[Path]:
    """Simpan diagram ke semua format yang diminta."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fig = build_figure()
    paths = []
    for fmt in formats:
        path = output_dir / f"{basename}.{fmt}"
        fig.savefig(path, dpi=300, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def parse_args():
    """Argumen CLI untuk folder output, basename, dan format file."""
    parser = argparse.ArgumentParser(
        description="Generate a static topology diagram for the Mininet Cyber Range."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated diagram files.",
    )
    parser.add_argument(
        "--basename",
        default=DEFAULT_BASENAME,
        help="Output filename without extension.",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["png", "pdf"],
        choices=["png", "pdf", "svg"],
        help="Output formats to write.",
    )
    return parser.parse_args()


def main():
    """Entry point generator diagram."""
    args = parse_args()
    paths = save_diagram(args.output_dir, args.basename, args.formats)
    for path in paths:
        print(f"Saved {path}")


if __name__ == "__main__":
    main()

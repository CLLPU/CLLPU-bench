"""Plot source-language MIA and overall Belebele results."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "multilingual_unlearning_mpl")
)

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


N_LANGUAGES = 10
METHOD_ORDER = [
    "Original",
    "Retrain",
    "GA",
    "GD",
    "NPO",
    "SimNPO",
    "BalDRO-NPO",
    "BalDRO-SimNPO",
]
MIA_METRICS = {
    "loss_auc_src": ("Loss", "o", "#4E79A7"),
    "min_k_auc_src": ("Min-K%", "s", "#F28E2B"),
    "min_k_pp_auc_src": ("Min-K%++", "D", "#59A14F"),
    "zlib_auc_src": ("Zlib", "^", "#B07AA1"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=Path(__file__).with_name("other_metrics_summary.tsv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("figures"),
    )
    parser.add_argument(
        "--name",
        default="mia_and_belebele",
    )
    return parser.parse_args()


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["STIXGeneral", "Times New Roman", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "font.size": 9.0,
            "axes.titlesize": 10.5,
            "axes.titleweight": "bold",
            "axes.labelsize": 9.5,
            "axes.labelweight": "bold",
            "xtick.labelsize": 8.2,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.5,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.bbox": "tight",
            "savefig.facecolor": "white",
        }
    )


def ordered(frame: pd.DataFrame, scenario: str) -> pd.DataFrame:
    result = frame.loc[frame["scenario"] == scenario].copy()
    available = [method for method in METHOD_ORDER if method in set(result["method"])]
    return result.set_index("method").loc[available].reset_index()


def style_method_ticks(ax: mpl.axes.Axes, methods: list[str]) -> None:
    for label, method in zip(ax.get_xticklabels(), methods):
        if method in {"Original", "Retrain"}:
            label.set_color("#777777")


def plot_mia(ax: mpl.axes.Axes, frame: pd.DataFrame, scenario: str) -> None:
    data = ordered(frame, scenario)
    methods = data["method"].tolist()
    x = np.arange(len(methods), dtype=float)
    offsets = np.linspace(-0.24, 0.24, len(MIA_METRICS))

    for offset, (column, (label, marker, color)) in zip(offsets, MIA_METRICS.items()):
        ax.scatter(
            x + offset,
            data[column],
            s=34,
            marker=marker,
            color=color,
            edgecolor="white",
            linewidth=0.5,
            label=label,
            zorder=3,
        )

    ax.axhline(0.5, color="#303030", linewidth=1.0, linestyle=(0, (4, 3)), zorder=1)
    ax.text(
        0.99,
        0.515,
        "Random discrimination",
        transform=ax.get_yaxis_transform(),
        ha="right",
        va="bottom",
        fontsize=8.2,
        color="#404040",
    )
    reference_count = sum(method in {"Original", "Retrain"} for method in methods)
    if reference_count:
        ax.axvline(reference_count - 0.5, color="#D3D3D3", linewidth=0.8)

    setting = "Common-goal" if scenario == "common" else "Culture-specific"
    ax.set_title(f"{setting}: Membership Inference")
    ax.set_ylabel("ROC-AUC")
    ax.set_ylim(0.10, 1.02)
    ax.set_yticks(np.arange(0.2, 1.01, 0.2))
    ax.set_xticks(x)
    ax.set_xticklabels(methods, rotation=25, ha="right")
    style_method_ticks(ax, methods)
    ax.grid(axis="y", color="#E6E6E6", linewidth=0.65)
    ax.set_axisbelow(True)


def plot_belebele(ax: mpl.axes.Axes, frame: pd.DataFrame, scenario: str) -> None:
    data = ordered(frame, scenario)
    methods = data["method"].tolist()
    data["belebele_acc_all"] = (
        data["belebele_acc_src"]
        + (N_LANGUAGES - 1) * data["belebele_acc_cross"]
    ) / N_LANGUAGES

    colors = [
        "#B8B8B8" if method in {"Original", "Retrain"} else "#4E8D9A"
        for method in methods
    ]
    x = np.arange(len(methods))
    bars = ax.bar(
        x,
        data["belebele_acc_all"],
        width=0.68,
        color=colors,
        edgecolor="white",
        linewidth=0.5,
    )

    for bar, value in zip(bars, data["belebele_acc_all"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.008,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=7.7,
        )

    reference_count = sum(method in {"Original", "Retrain"} for method in methods)
    if reference_count:
        ax.axvline(reference_count - 0.5, color="#D3D3D3", linewidth=0.8)

    setting = "Common-goal" if scenario == "common" else "Culture-specific"
    ax.set_title(f"{setting}: Multilingual Utility")
    ax.set_ylabel("Overall Belebele accuracy")
    ax.set_ylim(0.45, 0.85)
    ax.set_yticks(np.arange(0.5, 0.86, 0.1))
    ax.set_xticks(x)
    ax.set_xticklabels(methods, rotation=25, ha="right")
    style_method_ticks(ax, methods)
    ax.grid(axis="y", color="#E6E6E6", linewidth=0.65)
    ax.set_axisbelow(True)


def plot(frame: pd.DataFrame, output_dir: Path, name: str) -> None:
    configure_style()
    fig, axes = plt.subplots(
        2,
        2,
        figsize=(12.6, 7.0),
        gridspec_kw={"height_ratios": [1.05, 0.95], "hspace": 0.46, "wspace": 0.18},
    )

    plot_mia(axes[0, 0], frame, "common")
    plot_mia(axes[0, 1], frame, "culture")
    plot_belebele(axes[1, 0], frame, "common")
    plot_belebele(axes[1, 1], frame, "culture")

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, 0.995),
        columnspacing=1.4,
        handletextpad=0.45,
    )
    fig.subplots_adjust(left=0.065, right=0.99, bottom=0.12, top=0.92)

    output_dir.mkdir(parents=True, exist_ok=True)
    for extension in ("pdf", "svg", "png"):
        fig.savefig(
            output_dir / f"{name}.{extension}",
            dpi=600 if extension == "png" else None,
        )
    plt.close(fig)


def main() -> None:
    args = parse_args()
    frame = pd.read_csv(args.input, sep=None, engine="python")
    plot(frame, args.output_dir, args.name)


if __name__ == "__main__":
    main()

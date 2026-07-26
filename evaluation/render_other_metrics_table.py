"""Render a publication-style preview of MIA and Belebele results."""

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
import pandas as pd


N_LANGUAGES = 10
METHODS = [
    "Original",
    "Retrain",
    "GA",
    "GD",
    "NPO",
    "SimNPO",
    "BalDRO-NPO",
    "BalDRO-SimNPO",
]
METRICS = [
    "loss_auc_src",
    "min_k_auc_src",
    "min_k_pp_auc_src",
    "zlib_auc_src",
    "belebele_acc_all",
]
METRIC_LABELS = ["Loss", "Min-K%", "Min-K%++", "Zlib", "Belebele"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("other_metrics_summary.tsv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("figures"),
    )
    parser.add_argument("--name", default="other_metrics_table_preview")
    return parser.parse_args()


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["STIXGeneral", "Times New Roman", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "font.size": 10,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.bbox": "tight",
            "savefig.facecolor": "white",
        }
    )


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["belebele_acc_all"] = (
        result["belebele_acc_src"]
        + (N_LANGUAGES - 1) * result["belebele_acc_cross"]
    ) / N_LANGUAGES
    return result.set_index(["scenario", "method"])


def ranks(frame: pd.DataFrame, scenario: str, metric: str) -> tuple[str, str]:
    candidates = [
        method
        for method in METHODS
        if method not in {"Original", "Retrain"} and (scenario, method) in frame.index
    ]
    values = frame.loc[[(scenario, method) for method in candidates], metric]
    if metric.endswith("auc_src"):
        score = (values - 0.5).abs()
        ordered = score.sort_values(ascending=True).index
    else:
        ordered = values.sort_values(ascending=False).index
    return ordered[0][1], ordered[1][1]


def draw_rule(ax, x0, x1, y, width=0.8, color="#222222") -> None:
    ax.plot([x0, x1], [y, y], color=color, linewidth=width, solid_capstyle="butt")


def render(frame: pd.DataFrame, output_dir: Path, name: str) -> None:
    configure_style()
    data = prepare(frame)

    method_width = 2.15
    metric_widths = [1.03, 1.08, 1.16, 1.03, 1.20]
    column_widths = [method_width] + metric_widths + metric_widths
    x_edges = [0.0]
    for width in column_widths:
        x_edges.append(x_edges[-1] + width)
    total_width = x_edges[-1]

    header_heights = [0.66, 0.60, 0.62]
    row_height = 0.64
    total_height = sum(header_heights) + len(METHODS) * row_height

    fig, ax = plt.subplots(figsize=(14.3, 5.8))
    ax.set_xlim(0, total_width)
    ax.set_ylim(0, total_height)
    ax.axis("off")

    y_top = total_height
    header1_bottom = y_top - header_heights[0]
    header2_bottom = header1_bottom - header_heights[1]
    header3_bottom = header2_bottom - header_heights[2]

    draw_rule(ax, 0, total_width, y_top, width=1.35)
    draw_rule(ax, 0, total_width, header3_bottom, width=0.95)

    # Method spans all three header rows.
    ax.text(
        (x_edges[0] + x_edges[1]) / 2,
        (y_top + header3_bottom) / 2,
        "Method",
        ha="center",
        va="center",
        fontweight="bold",
        fontsize=10.5,
    )

    group_ranges = {
        "Common-goal": (x_edges[1], x_edges[6]),
        "Culture-specific": (x_edges[6], x_edges[11]),
    }
    for label, (left, right) in group_ranges.items():
        ax.text(
            (left + right) / 2,
            (y_top + header1_bottom) / 2,
            label,
            ha="center",
            va="center",
            fontweight="bold",
            fontsize=11,
        )
        draw_rule(ax, left + 0.08, right - 0.08, header1_bottom, width=0.72)

    # Second header level.
    for start in (1, 6):
        mia_left, mia_right = x_edges[start], x_edges[start + 4]
        utility_left, utility_right = x_edges[start + 4], x_edges[start + 5]
        ax.text(
            (mia_left + mia_right) / 2,
            (header1_bottom + header2_bottom) / 2,
            "Membership Inference (AUC → 0.5)",
            ha="center",
            va="center",
            fontweight="bold",
            fontsize=9.6,
        )
        ax.text(
            (utility_left + utility_right) / 2,
            (header1_bottom + header2_bottom) / 2,
            "Utility (↑)",
            ha="center",
            va="center",
            fontweight="bold",
            fontsize=9.6,
        )
        draw_rule(ax, mia_left + 0.07, mia_right - 0.07, header2_bottom, width=0.55)
        draw_rule(
            ax, utility_left + 0.07, utility_right - 0.07, header2_bottom, width=0.55
        )

    # Third header level.
    for group_start in (1, 6):
        for offset, label in enumerate(METRIC_LABELS):
            column = group_start + offset
            ax.text(
                (x_edges[column] + x_edges[column + 1]) / 2,
                (header2_bottom + header3_bottom) / 2,
                label,
                ha="center",
                va="center",
                fontweight="bold",
                fontsize=9.3,
            )

    # Restrained separators between semantic groups.
    for x in (x_edges[1], x_edges[6]):
        ax.plot(
            [x, x],
            [0, y_top],
            color="#D6D6D6",
            linewidth=0.65,
            zorder=0,
        )
    for x in (x_edges[5], x_edges[10]):
        ax.plot(
            [x, x],
            [header3_bottom, header1_bottom],
            color="#E2E2E2",
            linewidth=0.55,
            zorder=0,
        )

    rank_cache = {
        (scenario, metric): ranks(data, scenario, metric)
        for scenario in ("common", "culture")
        for metric in METRICS
    }

    for row_index, method in enumerate(METHODS):
        row_top = header3_bottom - row_index * row_height
        row_bottom = row_top - row_height
        y = (row_top + row_bottom) / 2
        is_reference = method in {"Original", "Retrain"}
        text_color = "#777777" if is_reference else "#1D1D1D"

        ax.text(
            x_edges[0] + 0.12,
            y,
            method,
            ha="left",
            va="center",
            color=text_color,
            fontsize=10,
        )

        for scenario_index, scenario in enumerate(("common", "culture")):
            for metric_index, metric in enumerate(METRICS):
                column = 1 + scenario_index * 5 + metric_index
                center = (x_edges[column] + x_edges[column + 1]) / 2
                key = (scenario, method)
                if key not in data.index:
                    display = "—"
                    value = None
                else:
                    value = float(data.loc[key, metric])
                    display = f"{value:.4f}"

                best, second = rank_cache[(scenario, metric)]
                weight = "bold" if method == best else "normal"
                ax.text(
                    center,
                    y,
                    display,
                    ha="center",
                    va="center",
                    color=text_color,
                    fontweight=weight,
                    fontsize=9.7,
                )
                if method == second and value is not None:
                    underline_width = 0.43
                    ax.plot(
                        [center - underline_width / 2, center + underline_width / 2],
                        [y - 0.17, y - 0.17],
                        color=text_color,
                        linewidth=0.65,
                    )

        if row_index == 1:
            draw_rule(ax, 0, total_width, row_bottom, width=0.82, color="#555555")

    draw_rule(ax, 0, total_width, 0, width=1.35)

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
    render(frame, args.output_dir, args.name)


if __name__ == "__main__":
    main()

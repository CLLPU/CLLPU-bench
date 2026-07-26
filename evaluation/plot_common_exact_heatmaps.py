"""Plot common-goal exact-match accessibility for forget and retain knowledge.

Example
-------
python evaluation/plot_common_exact_heatmaps.py forget.tsv retain.tsv \
    --output-dir evaluation/figures
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import tempfile

# Keep headless runs independent of a desktop GUI and user-level config access.
os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "multilingual_unlearning_mpl")
)

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd
import seaborn as sns


LANGUAGES = ["en", "zh", "de", "es", "fr", "ja", "ar", "th", "bn", "sw"]
METHODS = ["ga", "gd", "npo", "simnpo", "drnpo", "drsimnpo"]
METHOD_LABELS = {
    "ga": "GA",
    "gd": "GD",
    "npo": "NPO",
    "simnpo": "SimNPO",
    "drnpo": "BalDRO-NPO",
    "drsimnpo": "BalDRO-SimNPO",
}
SCENARIO = "common"
FORGET_METRIC = "A_current_exact_target_weighted_equal_forms"
RETAIN_METRIC = "A_current_exact_neighbor_weighted_equal_forms"
LEFT_BLOCK_TITLE = "Forget Quality"
RIGHT_BLOCK_TITLE = "Model Utility"
X_AXIS_TITLE = "Evaluation language"
Y_AXIS_TITLE = "Source language"
COLORBAR_TITLE = "Knowledge Accessibility"

# Typography after the figure is scaled to a two-column paper width.
LANGUAGE_TICK_SIZE = 8.1
METHOD_TITLE_SIZE = 9.2
GROUP_TITLE_SIZE = 10.0
AXIS_TITLE_SIZE = 10.0
COLORBAR_TITLE_SIZE = 10.0
COLORBAR_TICK_SIZE = 9.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot two 2x3 blocks of source-by-evaluation heatmaps for "
            "common-goal forget and retain exact-match accessibility."
        )
    )
    parser.add_argument("forget_input", type=Path, help="Forget-side TSV/CSV file.")
    parser.add_argument("retain_input", type=Path, help="Retain-side TSV/CSV file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("figures"),
        help="Output directory.",
    )
    parser.add_argument(
        "--name",
        default="common_goal_exact_forget_retain_heatmaps",
        help="Output filename stem.",
    )
    parser.add_argument(
        "--annotate",
        action="store_true",
        help="Print two-decimal values inside cells.",
    )
    parser.add_argument(
        "--vmin",
        type=float,
        default=None,
        help="Shared color minimum; defaults to the combined data minimum.",
    )
    parser.add_argument(
        "--vmax",
        type=float,
        default=None,
        help="Shared color maximum; defaults to the combined data maximum.",
    )
    parser.add_argument("--left-title", default=LEFT_BLOCK_TITLE)
    parser.add_argument("--right-title", default=RIGHT_BLOCK_TITLE)
    parser.add_argument("--x-label", default=X_AXIS_TITLE)
    parser.add_argument("--y-label", default=Y_AXIS_TITLE)
    parser.add_argument("--colorbar-label", default=COLORBAR_TITLE)
    return parser.parse_args()


def read_and_validate(path: Path, metric: str, role: str) -> pd.DataFrame:
    """Read one side of the figure and enforce a complete 6 x 10 x 10 grid."""
    df = pd.read_csv(path, sep=None, engine="python")
    required = {
        "scenario",
        "metric",
        "method",
        "source_language",
        "target_language",
        "value",
    }
    missing_columns = required.difference(df.columns)
    if missing_columns:
        raise ValueError(f"{role}: missing columns {sorted(missing_columns)}")

    df = df.loc[
        (df["scenario"] == SCENARIO)
        & (df["metric"] == metric)
        & (df["method"].isin(METHODS))
        & (df["source_language"].isin(LANGUAGES))
        & (df["target_language"].isin(LANGUAGES))
    ].copy()
    df["value"] = pd.to_numeric(df["value"], errors="raise")

    duplicated = df.duplicated(
        ["method", "source_language", "target_language"], keep=False
    )
    if duplicated.any():
        rows = df.loc[
            duplicated, ["method", "source_language", "target_language"]
        ]
        raise ValueError(
            f"{role}: duplicate method-language pairs found:\n"
            f"{rows.to_string(index=False)}"
        )

    expected = len(METHODS) * len(LANGUAGES) ** 2
    if len(df) != expected:
        counts = df.groupby("method").size().reindex(METHODS, fill_value=0)
        raise ValueError(
            f"{role}: expected {expected} rows but found {len(df)}. "
            f"Per-method counts:\n{counts}"
        )
    if not np.isfinite(df["value"]).all():
        raise ValueError(f"{role}: accessibility values must be finite.")
    return df


def make_colormap() -> LinearSegmentedColormap:
    # One perceptually ordered scale: dark/cool = low, warm/light = high.
    colors = ["#17324D", "#276C8E", "#58A6A6", "#E5BD62", "#FFF3D6"]
    return LinearSegmentedColormap.from_list("knowledge_accessibility", colors, N=256)


def matrix_for(df: pd.DataFrame, method: str) -> pd.DataFrame:
    matrix = df.loc[df["method"] == method].pivot(
        index="source_language", columns="target_language", values="value"
    )
    return matrix.reindex(index=LANGUAGES, columns=LANGUAGES)


def add_diagonal_outlines(ax: mpl.axes.Axes) -> None:
    """Outline source-language cells (s=t) without changing their colors."""
    for index in range(len(LANGUAGES)):
        ax.add_patch(
            Rectangle(
                (index, index),
                1,
                1,
                fill=False,
                edgecolor="#202124",
                linewidth=0.78,
                joinstyle="miter",
                zorder=5,
            )
        )


def add_cell_values(
    ax: mpl.axes.Axes,
    matrix: pd.DataFrame,
    cmap: mpl.colors.Colormap,
    norm: Normalize,
) -> None:
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = float(matrix.iat[row, column])
            red, green, blue, _ = cmap(norm(value))
            luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
            text_color = "#FFFFFF" if luminance < 0.48 else "#202124"
            ax.text(
                column + 0.5,
                row + 0.5,
                f"{value:.2f}",
                ha="center",
                va="center",
                fontsize=3.9,
                color=text_color,
            )


def configure_style() -> None:
    sns.set_theme(style="white", context="paper")
    mpl.rcParams.update(
        {
            # STIX closely matches the serif and mathematical typography used
            # by LaTeX while remaining self-contained (no TeX installation).
            "font.family": "serif",
            "font.serif": ["STIXGeneral", "Times New Roman", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "font.size": 9.0,
            "axes.titlesize": METHOD_TITLE_SIZE,
            "axes.titleweight": "bold",
            "axes.labelsize": AXIS_TITLE_SIZE,
            "xtick.labelsize": LANGUAGE_TICK_SIZE,
            "ytick.labelsize": LANGUAGE_TICK_SIZE,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.bbox": "tight",
            "savefig.facecolor": "white",
        }
    )


def rounded_limits(
    forget_df: pd.DataFrame,
    retain_df: pd.DataFrame,
    vmin: float | None,
    vmax: float | None,
) -> tuple[float, float]:
    combined = pd.concat([forget_df["value"], retain_df["value"]], ignore_index=True)
    step = 0.05
    if vmin is None:
        vmin = math.floor(float(combined.min()) / step) * step
    if vmax is None:
        vmax = math.ceil(float(combined.max()) / step) * step
    if vmin >= vmax:
        raise ValueError(f"Require vmin < vmax; got {vmin=}, {vmax=}.")
    return vmin, vmax


def draw_block(
    fig: mpl.figure.Figure,
    grid: mpl.gridspec.GridSpec,
    columns: tuple[int, int, int],
    df: pd.DataFrame,
    cmap: mpl.colors.Colormap,
    norm: Normalize,
    annotate: bool,
    show_y_labels: bool,
) -> list[mpl.axes.Axes]:
    axes: list[mpl.axes.Axes] = []
    tick_labels = [language.upper() for language in LANGUAGES]

    for method_index, method in enumerate(METHODS):
        row, local_column = divmod(method_index, 3)
        ax = fig.add_subplot(grid[row, columns[local_column]])
        axes.append(ax)
        matrix = matrix_for(df, method)
        sns.heatmap(
            matrix,
            ax=ax,
            cmap=cmap,
            norm=norm,
            square=True,
            cbar=False,
            linewidths=0.25,
            linecolor="#FFFFFF",
            xticklabels=tick_labels,
            yticklabels=tick_labels,
            rasterized=False,
        )
        add_diagonal_outlines(ax)
        if annotate:
            add_cell_values(ax, matrix, cmap, norm)

        ax.set_title(METHOD_LABELS[method], pad=3.5)
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.tick_params(axis="both", length=0, pad=1.2)
        if row == 0:
            ax.set_xticklabels([])
        else:
            ax.set_xticklabels(
                tick_labels,
                rotation=45,
                ha="right",
                rotation_mode="anchor",
            )
        if show_y_labels and local_column == 0:
            ax.set_yticklabels(tick_labels, rotation=0)
        else:
            ax.set_yticklabels([])
        for spine in ax.spines.values():
            spine.set_visible(False)
    return axes


def plot(
    forget_df: pd.DataFrame,
    retain_df: pd.DataFrame,
    output_dir: Path,
    name: str,
    annotate: bool,
    vmin: float | None,
    vmax: float | None,
    left_title: str,
    right_title: str,
    x_label: str,
    y_label: str,
    colorbar_label: str,
) -> None:
    configure_style()
    cmap = make_colormap()
    vmin, vmax = rounded_limits(forget_df, retain_df, vmin, vmax)
    norm = Normalize(vmin=vmin, vmax=vmax)

    figure_size = (14.7, 5.00) if annotate else (12.6, 4.35)
    fig = plt.figure(figsize=figure_size)
    grid = fig.add_gridspec(
        2,
        8,
        width_ratios=[1, 1, 1, 0.075, 1, 1, 1, 0.040],
        left=0.050,
        right=0.960,
        bottom=0.130,
        top=0.905,
        wspace=0.040,
        hspace=0.115,
    )

    draw_block(
        fig,
        grid,
        columns=(0, 1, 2),
        df=forget_df,
        cmap=cmap,
        norm=norm,
        annotate=annotate,
        show_y_labels=True,
    )
    draw_block(
        fig,
        grid,
        columns=(4, 5, 6),
        df=retain_df,
        cmap=cmap,
        norm=norm,
        annotate=annotate,
        show_y_labels=False,
    )

    color_axis = fig.add_subplot(grid[:, 7])
    scalar_mappable = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    scalar_mappable.set_array([])
    colorbar = fig.colorbar(scalar_mappable, cax=color_axis)
    colorbar.set_label(
        colorbar_label,
        rotation=90,
        labelpad=8,
        fontsize=COLORBAR_TITLE_SIZE,
        fontweight="bold",
    )
    # Keep the upper part of the vertical label area empty for a formula overlay.
    colorbar.ax.yaxis.set_label_coords(5.50, 0.40)
    colorbar.outline.set_linewidth(0.5)
    colorbar.ax.tick_params(
        length=2.5,
        width=0.5,
        pad=2,
        labelsize=COLORBAR_TICK_SIZE,
    )
    colorbar.set_ticks(np.linspace(vmin, vmax, 7))
    colorbar.ax.yaxis.set_major_formatter(mpl.ticker.FormatStrFormatter("%.2f"))

    # Block headings and a restrained divider make the 2x3 + 2x3 structure explicit.
    fig.text(
        0.269,
        0.952,
        left_title,
        ha="right",
        va="center",
        fontsize=GROUP_TITLE_SIZE,
        fontweight="bold",
    )
    fig.text(
        0.714,
        0.952,
        right_title,
        ha="right",
        va="center",
        fontsize=GROUP_TITLE_SIZE,
        fontweight="bold",
    )
    fig.add_artist(
        Line2D(
            [0.482, 0.482],
            [0.095, 0.905],
            transform=fig.transFigure,
            color="#D0D4D8",
            linewidth=0.65,
        )
    )

    # Text is shifted slightly before its visual center so that screenshots of
    # the corresponding mathematical symbols can be inserted after each label.
    fig.supxlabel(
        x_label,
        x=0.500,
        y=0.035,
        ha="right",
        fontsize=AXIS_TITLE_SIZE,
        fontweight="bold",
    )
    fig.supylabel(
        y_label,
        x=0.023,
        y=0.468,
        fontsize=AXIS_TITLE_SIZE,
        fontweight="bold",
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for extension in ("pdf", "svg", "png"):
        destination = output_dir / f"{name}.{extension}"
        fig.savefig(destination, dpi=600 if extension == "png" else None)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    forget_df = read_and_validate(args.forget_input, FORGET_METRIC, "forget")
    retain_df = read_and_validate(args.retain_input, RETAIN_METRIC, "retain")
    plot(
        forget_df,
        retain_df,
        output_dir=args.output_dir,
        name=args.name,
        annotate=args.annotate,
        vmin=args.vmin,
        vmax=args.vmax,
        left_title=args.left_title,
        right_title=args.right_title,
        x_label=args.x_label,
        y_label=args.y_label,
        colorbar_label=args.colorbar_label,
    )


if __name__ == "__main__":
    main()

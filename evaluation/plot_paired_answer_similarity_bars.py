"""Plot source-only paired-answer similarity for the two benchmark settings.

The pasted input contains two side-by-side exports:
1) ten common-goal scores in the first column; and
2) a complete language-conditioned source-by-evaluation table in columns 4--12.

Only the source-language entries are plotted. Cross-language entries are ignored.
"""

from __future__ import annotations

import argparse
import csv
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


LANGUAGES = ["en", "zh", "de", "es", "fr", "ja", "ar", "th", "bn", "sw"]
INPUT_LANGUAGE_ORDER = ["ar", "bn", "de", "en", "es", "fr", "ja", "sw", "th", "zh"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot source-only paired expected-answer similarity."
    )
    parser.add_argument("input", type=Path, help="Pasted tab-separated input file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/figures/user_code_run"),
    )
    parser.add_argument(
        "--name",
        default="paired_expected_answer_similarity_source_bars",
    )
    return parser.parse_args()


def read_scores(path: Path) -> tuple[dict[str, float], dict[str, float]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))

    if len(rows) < 11:
        raise ValueError("The input does not contain the ten common-goal scores.")

    common_values = []
    for row in rows[1:]:
        if row and row[0].strip():
            common_values.append(float(row[0]))
    if len(common_values) != len(INPUT_LANGUAGE_ORDER):
        raise ValueError(
            "Expected exactly ten common-goal scores in the first column, "
            f"but found {len(common_values)}."
        )
    common = dict(zip(INPUT_LANGUAGE_ORDER, common_values, strict=True))

    conditioned: dict[str, float] = {}
    for row in rows[1:]:
        if len(row) < 12 or row[3].strip() != "culture_specific":
            continue
        source_language = row[5].strip()
        evaluation_language = row[6].strip()
        scope = row[8].strip()
        if scope == "source" and source_language == evaluation_language:
            conditioned[source_language] = float(row[11])

    missing = set(LANGUAGES).difference(conditioned)
    if missing:
        raise ValueError(
            "Missing language-conditioned source scores for: "
            + ", ".join(sorted(missing))
        )
    return common, conditioned


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["STIXGeneral", "Times New Roman", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "font.size": 10.0,
            "axes.titlesize": 11.0,
            "axes.titleweight": "bold",
            "axes.labelsize": 10.5,
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.facecolor": "white",
        }
    )


def draw_panel(
    ax: mpl.axes.Axes,
    values: list[float],
    title: str,
    color: str,
) -> None:
    positions = np.arange(len(LANGUAGES))
    ax.bar(
        positions,
        values,
        width=0.68,
        color=color,
        edgecolor="#263238",
        linewidth=0.55,
        zorder=3,
    )
    ax.set_title(title, pad=8)
    ax.set_xticks(positions, [language.upper() for language in LANGUAGES])
    ax.set_ylim(0.0, 0.65)
    ax.set_yticks(np.arange(0.0, 0.61, 0.1))
    ax.grid(axis="y", color="#D8DEE3", linewidth=0.65, alpha=0.9, zorder=0)
    ax.tick_params(axis="x", length=0, pad=4)
    ax.tick_params(axis="y", length=3, width=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#6B747C")
    ax.spines["bottom"].set_color("#6B747C")
    ax.spines["left"].set_linewidth(0.7)
    ax.spines["bottom"].set_linewidth(0.7)


def main() -> None:
    args = parse_args()
    common, conditioned = read_scores(args.input)
    configure_style()

    common_values = [common[language] for language in LANGUAGES]
    conditioned_values = [conditioned[language] for language in LANGUAGES]

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(10.2, 3.05),
        sharey=True,
        gridspec_kw={"wspace": 0.10},
    )
    draw_panel(axes[0], common_values, "Common-goal", "#3F7CAC")
    draw_panel(
        axes[1],
        conditioned_values,
        "Language-conditioned",
        "#D28B45",
    )
    axes[0].set_ylabel("Paired Expected-Answer Similarity")
    fig.supxlabel("Language", y=0.035, fontsize=10.5, fontweight="bold")
    fig.subplots_adjust(left=0.085, right=0.99, bottom=0.20, top=0.88)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for extension in ("pdf", "png"):
        output = args.output_dir / f"{args.name}.{extension}"
        fig.savefig(output, dpi=320, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


if __name__ == "__main__":
    main()

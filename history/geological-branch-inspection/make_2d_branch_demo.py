from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parent
SURVEY_FILE = ROOT / "drilling" / "E 38_2362_WADS4_SURV2015A.txt"
OUTPUT_FILE = ROOT / "15EIS001_2d_branch_demo.jpg"


def load_rows(path: Path) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("D\t"):
            continue
        fields = line.split("\t")
        rows.append(
            {
                "md": float(fields[3]),
                "method": fields[4],
                "priority": int(fields[5]),
                "dip": float(fields[6]),
                "az": float(fields[8]),
                "date": fields[10],
                "comment": fields[15] if len(fields) > 15 else "",
            }
        )
    return rows


def minimum_curvature(
    stations: list[dict[str, float | str]],
    anchor: dict[str, float] | None = None,
) -> list[dict[str, float | str]]:
    anchor = anchor or {"east": 0.0, "north": 0.0, "tvd": 0.0}
    points = [{**stations[0], **anchor}]

    for previous_station, station in zip(stations, stations[1:]):
        previous_point = points[-1]
        delta_md = float(station["md"]) - float(previous_station["md"])
        inc1 = math.radians(90.0 + float(previous_station["dip"]))
        inc2 = math.radians(90.0 + float(station["dip"]))
        az1 = math.radians(float(previous_station["az"]))
        az2 = math.radians(float(station["az"]))

        cosine = (
            math.cos(inc1) * math.cos(inc2)
            + math.sin(inc1) * math.sin(inc2) * math.cos(az2 - az1)
        )
        dogleg = math.acos(max(-1.0, min(1.0, cosine)))
        ratio_factor = 1.0 if dogleg < 1e-12 else 2.0 / dogleg * math.tan(dogleg / 2.0)

        north = float(previous_point["north"]) + delta_md * 0.5 * (
            math.sin(inc1) * math.cos(az1) + math.sin(inc2) * math.cos(az2)
        ) * ratio_factor
        east = float(previous_point["east"]) + delta_md * 0.5 * (
            math.sin(inc1) * math.sin(az1) + math.sin(inc2) * math.sin(az2)
        ) * ratio_factor
        tvd = float(previous_point["tvd"]) + delta_md * 0.5 * (
            math.cos(inc1) + math.cos(inc2)
        ) * ratio_factor
        points.append({**station, "east": east, "north": north, "tvd": tvd})

    section_azimuth = math.radians(252.57)
    for point in points:
        point["offset"] = (
            float(point["east"]) * math.sin(section_azimuth)
            + float(point["north"]) * math.cos(section_azimuth)
        )
    return points


def interpolate(path: list[dict[str, float | str]], md: float) -> dict[str, float]:
    for left, right in zip(path, path[1:]):
        left_md = float(left["md"])
        right_md = float(right["md"])
        if left_md <= md <= right_md:
            fraction = (md - left_md) / (right_md - left_md)
            return {
                key: float(left[key]) + (float(right[key]) - float(left[key])) * fraction
                for key in ("east", "north", "tvd", "offset")
            }
    raise ValueError(f"MD {md} falls outside the final trajectory")


def make_branch(
    final_path: list[dict[str, float | str]],
    stations: list[tuple[float, float, float]],
) -> list[dict[str, float | str]]:
    records = [
        {"md": md, "dip": dip, "az": az, "method": "REFLEX"}
        for md, dip, az in stations
    ]
    return minimum_curvature(records, interpolate(final_path, stations[0][0]))


def xy(path: list[dict[str, float | str]]) -> tuple[list[float], list[float]]:
    return (
        [float(point["offset"]) for point in path],
        [float(point["tvd"]) for point in path],
    )


def main() -> None:
    rows = load_rows(SURVEY_FILE)
    gyro = sorted((row for row in rows if row["method"] == "GYRO"), key=lambda row: float(row["md"]))
    end_reflex = max((row for row in rows if row["method"] == "REFLEX"), key=lambda row: float(row["md"]))
    final_path = minimum_curvature([*gyro, end_reflex])

    branches = [
        (
            'Abandoned tail of the original main hole',
            183.4,
            make_branch(
                final_path,
                [(183.4, -62.1, 253.4), (210.4, -60.9, 252.3), (222.4, -60.6, 252.3)],
            ),
        ),
        (
            'Abandoned tail of the first branch',
            429.2,
            make_branch(
                final_path,
                [
                    (429.2, -56.3, 250.2),
                    (438.0, -56.3, 250.6),
                    (450.0, -56.4, 251.9),
                    (465.3, -54.0, 259.4),
                    (483.6, -53.3, 259.1),
                    (492.7, -56.3, 257.5),
                    (502.0, -56.3, 257.5),
                ],
            ),
        ),
        (
            'Abandoned tail of the second branch',
            494.5,
            make_branch(
                final_path,
                [(494.5, -54.6, 251.2), (498.2, -54.6, 251.2), (500.8, -54.6, 251.2)],
            ),
        ),
    ]

    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    if font_path.exists():
        font_manager.fontManager.addfont(font_path)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=font_path).get_name()
    plt.rcParams["axes.unicode_minus"] = False

    blue = "#1775b8"
    orange = "#d97706"
    purple = "#7c3aed"
    grid = "#d7dde5"
    text = "#17202a"

    figure, (full_axis, zoom_axis) = plt.subplots(1, 2, figsize=(16, 9), dpi=150)
    figure.patch.set_facecolor("white")
    figure.suptitle('15EIS001: 2D borehole trajectory and branches', fontsize=21, fontweight="bold", color=text, y=0.97)

    for axis, title in ((full_axis, 'Full borehole trajectory (0-1701.6 m)'), (zoom_axis, 'Branch detail in the upper 520 m')):
        axis.set_facecolor("white")
        axis.grid(True, color=grid, linewidth=0.8, alpha=0.8)
        axis.set_axisbelow(True)
        axis.set_title(title, fontsize=15, pad=12, color=text)
        axis.set_xlabel('Horizontal displacement along initial azimuth 252.6 degrees (m)', fontsize=12, color=text)
        axis.set_ylabel('True vertical depth, TVD (m)', fontsize=12, color=text)
        axis.tick_params(colors=text, labelsize=10)
        axis.set_aspect("equal", adjustable="box")
        axis.invert_yaxis()

        final_x, final_y = xy(final_path)
        axis.plot(final_x, final_y, color=blue, linewidth=3.2, label='Final accessible borehole path (GYRO)', zorder=3)
        for index, (label, split_md, branch) in enumerate(branches):
            branch_x, branch_y = xy(branch)
            axis.plot(
                branch_x,
                branch_y,
                color=orange,
                linewidth=2.4,
                linestyle=(0, (6, 4)),
                label='Abandoned tail sections (REFLEX approximation)' if index == 0 else None,
                zorder=4,
            )
            split = interpolate(final_path, split_md)
            axis.scatter(split["offset"], split["tvd"], s=58, color=purple, edgecolor="white", linewidth=1.2, zorder=6)

        axis.scatter(0, 0, s=55, color=text, zorder=7)

    full_axis.annotate('Collar', xy=(0, 0), xytext=(15, 24), textcoords="offset points", fontsize=11, color=text)
    end = final_path[-1]
    full_axis.annotate(
        "EOH 1701.6 m",
        xy=(float(end["offset"]), float(end["tvd"])),
        xytext=(-18, -22),
        textcoords="offset points",
        ha="right",
        fontsize=11,
        color=text,
        arrowprops={"arrowstyle": "-", "color": text, "linewidth": 0.9},
    )
    full_axis.text(
        0.63,
        0.96,
        '337 GYRO points at 5 m spacing\n+ REFLEX endpoint at 1701.6 m',
        transform=full_axis.transAxes,
        va="top",
        fontsize=11,
        color=text,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": grid},
    )

    zoom_axis.set_ylim(525, -15)
    zoom_axis.set_xlim(-18, 340)
    label_offsets = [(16, -26), (-20, 28), (20, 36)]
    for (label, split_md, branch), offset in zip(branches, label_offsets):
        split = interpolate(final_path, split_md)
        zoom_axis.annotate(
            f"{split_md:.1f} m\n{label}",
            xy=(split["offset"], split["tvd"]),
            xytext=offset,
            textcoords="offset points",
            fontsize=10,
            ha="left" if offset[0] > 0 else "right",
            va="center",
            color=text,
            arrowprops={"arrowstyle": "-", "color": purple, "linewidth": 1.0},
            bbox={"boxstyle": "square,pad=0.15", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
        )

    handles, labels = full_axis.get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=2, frameon=False, fontsize=12, bbox_to_anchor=(0.5, 0.052))
    figure.text(
        0.5,
        0.016,
        'Solid line: minimum-curvature calculation from official GYRO data. Dashed lines: approximate abandoned tails reconstructed from drilling sequence and REFLEX points.',
        ha="center",
        fontsize=11,
        color="#4b5563",
    )
    figure.subplots_adjust(left=0.07, right=0.97, top=0.90, bottom=0.15, wspace=0.22)
    figure.savefig(
        OUTPUT_FILE,
        format="jpg",
        dpi=180,
        facecolor="white",
        pil_kwargs={"quality": 94},
    )
    plt.close(figure)
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()

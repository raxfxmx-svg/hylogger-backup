from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image
from pytsg import parse_tsg


ROOT = Path(r"C:\path\to\project")
DATA_DIR = ROOT / "8a294cfc-68df-4f03-995b-c5fd0d47ab0"
PHOTO_PATH = DATA_DIR / "05GJD001_0008.jpg"
OUTPUT_PATH = ROOT / "05GJD001_tray_0008_exploration.png"


def main() -> None:
    data = parse_tsg.read_package(str(DATA_DIR))

    header = data.nir.sampleheaders
    scalars = data.nir.scalars
    mask = header["T"].astype(str).str.zfill(4).eq("0008")

    tray = pd.DataFrame(
        {
            "row": header.loc[mask, "L"].astype(int).to_numpy(),
            "x_mm": header.loc[mask, "X"].astype(float).to_numpy(),
            "depth_m": header.loc[mask, "D"].astype(float).to_numpy(),
            "mineral": scalars.loc[mask, "Min1 sTSAS"].astype(str).to_numpy(),
            "group": scalars.loc[mask, "Grp1 sTSAS"].astype(str).to_numpy(),
        }
    )
    tray["group"] = tray["group"].replace("", "NO RESULT")

    colors = {
        "CHLORITE": "#2ca02c",
        "CARBONATE": "#1f77b4",
        "DARK-MICA": "#795548",
        "WHITE-MICA": "#e6c84f",
        "AMPHIBOLE": "#9467bd",
        "EPIDOTE": "#17becf",
        "SULPHATE": "#ff7f0e",
        "SERPENTINE": "#8c564b",
        "OTHER-ALOH": "#e377c2",
        "INVALID": "#666666",
        "NO RESULT": "#dddddd",
    }

    with Image.open(PHOTO_PATH) as source:
        photo = source.convert("RGB")
        photo.thumbnail((1800, 900), Image.Resampling.LANCZOS)

    fig, (ax_photo, ax_map) = plt.subplots(
        2,
        1,
        figsize=(18, 9),
        gridspec_kw={"height_ratios": [3.6, 1.5]},
    )

    ax_photo.imshow(photo)
    ax_photo.set_title("05GJD001 - Tray 0008 - 185.5 to 190.2 m", fontsize=16)
    ax_photo.axis("off")

    for group, points in tray.groupby("group"):
        ax_map.scatter(
            points["x_mm"],
            points["row"],
            color=colors.get(group, "black"),
            marker="s",
            s=22,
            linewidths=0,
            label=group,
        )

    ax_map.set_xlim(0, 1050)
    ax_map.set_ylim(6.5, 0.5)
    ax_map.set_xticks(range(0, 1100, 100))
    ax_map.set_yticks(range(1, 7))
    ax_map.set_xlabel("Distance along each core row (mm)")
    ax_map.set_ylabel("Photo row")
    ax_map.set_title("TSG automatic mineral-group identification")
    ax_map.grid(alpha=0.2)
    ax_map.legend(
        title="Mineral group",
        bbox_to_anchor=(1.005, 1),
        loc="upper left",
        fontsize=8,
    )

    fig.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved: {OUTPUT_PATH}")
    print(f"TSG points: {len(tray)}")
    print(f"Depth range: {tray['depth_m'].min():.3f} to {tray['depth_m'].max():.3f} m")
    print("\nMineral groups:")
    print(tray["group"].value_counts().to_string())


if __name__ == "__main__":
    main()

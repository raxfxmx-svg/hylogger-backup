"""Extract auditable 05GJD001 records and web images from a local TSG package.

The browser uses compact CSV/JSON exports, not the large spectra arrays. Every
displayed depth and mineral group is derived from the supplied package. The
script does not invent coordinates or confidence values.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageOps
from pytsg import parse_tsg


GROUP_COLUMN = "Grp1 sTSAS"
DEFAULT_BIN_SIZE_M = 0.1


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_bundle", type=Path, help="Directory containing the local TSG package")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "data",
        help="Directory for compact CSV and JSON exports",
    )
    parser.add_argument(
        "--image-output-dir",
        type=Path,
        default=project_root / "assets" / "core",
        help="Directory for resized tray photographs",
    )
    parser.add_argument("--bin-size-m", type=float, default=DEFAULT_BIN_SIZE_M)
    return parser.parse_args()


def wavelength_range(layer) -> tuple[float | None, float | None]:
    if layer is None or getattr(layer, "wavelength", None) is None:
        return None, None
    wavelengths = np.asarray(layer.wavelength, dtype=float)
    return float(wavelengths.min()), float(wavelengths.max())


def build_sample_groups(headers: pd.DataFrame, scalars: pd.DataFrame) -> pd.DataFrame:
    if GROUP_COLUMN not in scalars.columns:
        raise ValueError(f"NIR scalar column not found: {GROUP_COLUMN}")

    return pd.DataFrame(
        {
            "sample_id": pd.to_numeric(headers["sample"], errors="raise").astype(int),
            "hole_id": headers["H"].astype(str).str.strip(),
            "tray_id": headers["T"].astype(str).str.zfill(4),
            "core_row": pd.to_numeric(headers["L"], errors="raise").astype(int),
            "position_index": pd.to_numeric(headers["P"], errors="raise").astype(int),
            "depth_m": pd.to_numeric(headers["D"], errors="raise").round(6),
            "along_row_mm": pd.to_numeric(headers["X"], errors="coerce").round(3),
            "mineral_group": scalars[GROUP_COLUMN].astype(str).str.strip().replace("", "NO RESULT"),
            "algorithm_field": GROUP_COLUMN,
        }
    )


def build_group_summary(samples: pd.DataFrame) -> pd.DataFrame:
    summary = (
        samples.groupby("mineral_group", dropna=False)
        .agg(
            sample_count=("sample_id", "size"),
            depth_min_m=("depth_m", "min"),
            depth_max_m=("depth_m", "max"),
        )
        .reset_index()
        .sort_values(["sample_count", "mineral_group"], ascending=[False, True])
        .reset_index(drop=True)
    )
    summary["share_pct"] = (summary["sample_count"] / len(samples) * 100).round(2)
    summary["depth_min_m"] = summary["depth_min_m"].round(3)
    summary["depth_max_m"] = summary["depth_max_m"].round(3)
    summary["algorithm_field"] = GROUP_COLUMN
    return summary


def build_tray_table(samples: pd.DataFrame) -> pd.DataFrame:
    return (
        samples.groupby(["hole_id", "tray_id"], sort=True)
        .agg(
            depth_from_m=("depth_m", "min"),
            depth_to_m=("depth_m", "max"),
            sample_count=("sample_id", "size"),
        )
        .reset_index()
        .sort_values(["depth_from_m", "tray_id"])
        .reset_index(drop=True)
    )


def build_depth_bins(samples: pd.DataFrame, trays: pd.DataFrame, bin_size_m: float) -> pd.DataFrame:
    if bin_size_m <= 0:
        raise ValueError("bin_size_m must be positive")

    working = samples[["hole_id", "tray_id", "depth_m", "mineral_group"]].copy()
    working["bin_index"] = np.floor((working["depth_m"] / bin_size_m) + 1e-7).astype("int64")
    group_counts = (
        working.groupby(["hole_id", "tray_id", "bin_index", "mineral_group"], sort=True)
        .size()
        .rename("dominant_sample_count")
        .reset_index()
    )
    totals = (
        working.groupby(["hole_id", "tray_id", "bin_index"], sort=True)
        .size()
        .rename("sample_count")
        .reset_index()
    )
    dominant = (
        group_counts.sort_values(
            ["hole_id", "tray_id", "bin_index", "dominant_sample_count", "mineral_group"],
            ascending=[True, True, True, False, True],
        )
        .drop_duplicates(["hole_id", "tray_id", "bin_index"], keep="first")
        .merge(totals, on=["hole_id", "tray_id", "bin_index"], how="left", validate="one_to_one")
    )
    tray_ranges = trays[["hole_id", "tray_id", "depth_from_m", "depth_to_m"]].rename(
        columns={"depth_from_m": "tray_depth_from_m", "depth_to_m": "tray_depth_to_m"}
    )
    dominant = dominant.merge(tray_ranges, on=["hole_id", "tray_id"], how="left", validate="many_to_one")
    bin_starts = dominant["bin_index"] * bin_size_m
    dominant["depth_from_m"] = np.maximum(bin_starts, dominant["tray_depth_from_m"]).round(6)
    dominant["depth_to_m"] = np.minimum(bin_starts + bin_size_m, dominant["tray_depth_to_m"]).round(6)
    dominant["dominant_share_pct"] = (
        dominant["dominant_sample_count"] / dominant["sample_count"] * 100
    ).round(2)
    dominant["bin_size_m"] = bin_size_m
    dominant["algorithm_field"] = GROUP_COLUMN
    dominant = dominant.loc[dominant["depth_to_m"] > dominant["depth_from_m"]]
    return dominant[
        [
            "hole_id",
            "tray_id",
            "depth_from_m",
            "depth_to_m",
            "mineral_group",
            "sample_count",
            "dominant_sample_count",
            "dominant_share_pct",
            "bin_size_m",
            "algorithm_field",
        ]
    ].sort_values(["depth_from_m", "tray_id"]).reset_index(drop=True)


def resize_tray_images(
    source_bundle: Path, image_output_dir: Path, hole_id: str, trays: pd.DataFrame
) -> pd.DataFrame:
    image_output_dir.mkdir(parents=True, exist_ok=True)
    updated = trays.copy()
    image_paths: list[str] = []
    image_statuses: list[str] = []
    image_widths: list[int | None] = []
    image_heights: list[int | None] = []

    for tray_id in updated["tray_id"]:
        source_path = source_bundle / f"{hole_id}_{tray_id}.jpg"
        output_name = f"{hole_id}_{tray_id}_web.jpg"
        output_path = image_output_dir / output_name
        if not source_path.is_file():
            image_paths.append("")
            image_statuses.append("missing")
            image_widths.append(None)
            image_heights.append(None)
            print(f"Warning: source image not found for tray {tray_id}: {source_path}")
            continue

        try:
            with Image.open(source_path) as original:
                image = ImageOps.exif_transpose(original).convert("RGB")
                image.thumbnail((1800, 900), Image.Resampling.LANCZOS)
                image.save(output_path, "JPEG", quality=82, optimize=True, progressive=True)
                width, height = image.size
            image_paths.append(f"core/{output_name}")
            image_statuses.append("available")
            image_widths.append(width)
            image_heights.append(height)
        except Exception as exc:
            image_paths.append("")
            image_statuses.append("unreadable")
            image_widths.append(None)
            image_heights.append(None)
            print(f"Warning: could not process tray {tray_id}: {exc}")

    updated["image_relpath"] = image_paths
    updated["image_status"] = image_statuses
    updated["image_width_px"] = image_widths
    updated["image_height_px"] = image_heights
    return updated


def main() -> None:
    args = parse_args()
    source_bundle = args.source_bundle.resolve()
    if not source_bundle.is_dir():
        raise FileNotFoundError(f"TSG package directory not found: {source_bundle}")

    package = parse_tsg.read_package(str(source_bundle))
    if package.nir is None:
        raise ValueError("The package does not contain a NIR layer")

    headers = package.nir.sampleheaders.reset_index(drop=True)
    scalars = package.nir.scalars.reset_index(drop=True)
    samples = build_sample_groups(headers, scalars)
    hole_ids = sorted(samples["hole_id"].unique().tolist())
    if len(hole_ids) != 1:
        raise ValueError(f"This explorer expects one hole per package; found {hole_ids}")
    hole_id = hole_ids[0]

    trays = build_tray_table(samples)
    trays = resize_tray_images(source_bundle, args.image_output_dir, hole_id, trays)
    depth_bins = build_depth_bins(samples, trays, args.bin_size_m)
    summary = build_group_summary(samples)

    holes = pd.DataFrame(
        [
            {
                "hole_id": hole_id,
                "hole_name": hole_id,
                "latitude": None,
                "longitude": None,
                "coordinate_status": "not_supplied",
                "source_bundle_id": source_bundle.name,
                "notes": "Coordinates are not present in the supplied package; fields are reserved for later data.",
            }
        ]
    )

    nir_min, nir_max = wavelength_range(package.nir)
    tir_min, tir_max = wavelength_range(package.tir)
    metadata = {
        "source_bundle_id": source_bundle.name,
        "hole_ids": hole_ids,
        "tray_count": int(len(trays)),
        "sample_count": int(len(samples)),
        "depth_min_m": round(float(samples["depth_m"].min()), 6),
        "depth_max_m": round(float(samples["depth_m"].max()), 6),
        "nir_channels": int(package.nir.spectra.shape[1]),
        "nir_wavelength_min_nm": nir_min,
        "nir_wavelength_max_nm": nir_max,
        "tir_channels": int(package.tir.spectra.shape[1]) if package.tir is not None else None,
        "tir_wavelength_min_nm": tir_min,
        "tir_wavelength_max_nm": tir_max,
        "group_algorithm_field": GROUP_COLUMN,
        "depth_bin_size_m": args.bin_size_m,
        "coordinate_status": "not_supplied",
        "confidence_status": "not_supplied_and_not_inferred",
        "provenance_note": (
            "Depths, tray membership, and NIR group labels were extracted from the supplied package. "
            "Coordinates and confidence values were not supplied and are not inferred."
        ),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    holes.to_csv(args.output_dir / "holes.csv", index=False)
    trays.to_csv(args.output_dir / f"{hole_id}_trays.csv", index=False)
    samples.to_csv(args.output_dir / f"{hole_id}_sample_groups.csv", index=False)
    depth_bins.to_csv(args.output_dir / f"{hole_id}_depth_bins.csv", index=False)
    summary.to_csv(args.output_dir / f"{hole_id}_scan_summary.csv", index=False)
    (args.output_dir / f"{hole_id}_scan_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Hole: {hole_id}")
    print(f"Depth: {metadata['depth_min_m']:.3f} to {metadata['depth_max_m']:.3f} m")
    print(f"Samples: {metadata['sample_count']}; trays: {metadata['tray_count']}")
    print(f"Depth bins: {len(depth_bins)}; mineral groups: {len(summary)}")
    print(f"Web images available: {(trays['image_status'] == 'available').sum()} / {len(trays)}")


if __name__ == "__main__":
    main()

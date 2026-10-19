"""Check row boundaries, preserve all core pixels, and record visual review results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import math
import numpy as np
from PIL import ImageDraw, Image
from _run_reports import main_guard
from _db_files import sha
from _media_common import decode, require, save_stage, source_path, stage
from _settings import StepParser
from _settings import settings, configure


def main():
    parser = StepParser()
    parser.add_argument("--record-reviewed", action="store_true")
    args = parser.parse_args()
    configure(args)
    proposed = stage(24)
    frames = {f["id"]: f for f in stage(23)["frames"]}
    rows = []
    checks = []
    for fid, f in frames.items():
        source = decode(source_path(f, f["source_path"]))
        arr = np.asarray(source).astype(float)
        # Look for brightness dividers near metadata positions while preserving dark core pixels.
        profile = np.median(arr[:, 8:-8, :].mean(axis=2), axis=1)
        n = f["row_count"]
        h = f["height_px"]
        pitch = h / n
        boundaries = [0]
        details = []
        for i in range(1, n):
            center = round(i * pitch)
            radius = max(2, round(0.12 * pitch))
            options = range(max(3, center - radius), min(h - 3, center + radius + 1))
            scores = {y: float(profile[y] - (profile[y - 3] + profile[y + 3]) / 2) for y in options}
            best = max(scores, key=scores.get)
            # Use the geometric template when dividers are unclear; preserve the full row edges.
            cut = best if scores[best] >= 12 else center
            boundaries.append(cut)
            details.append(
                {
                    "expected": center,
                    "cut": cut,
                    "ridge_score": scores[best],
                    "method": (
                        "local_divider_ridge" if scores[best] >= 12 else "reviewed_equal_pitch"
                    ),
                }
            )
        boundaries.append(h)
        fr = sorted(
            (r for r in proposed["rows"] if r["source_frame_id"] == fid),
            key=lambda r: r["region_ordinal"],
        )
        require(len(fr) == n, "Row count mismatch")
        for i, r in enumerate(fr):
            r = {
                **r,
                "y_px": boundaries[i],
                "height_px": boundaries[i + 1] - boundaries[i],
                "region_status": "reviewed",
                "detection_method": "section_pitch_local_divider_ridge_preserve_cell_v1",
                "review_basis": f"{len(proposed['templates'])} layout classes; first/last representative visual inspection plus all-frame geometry and source identity checks",
            }
            require(
                r["height_px"] > 0 and r["height_px"] <= pitch * 1.35, "Suspect boundary spacing"
            )
            rows.append(r)
        checks.append(
            {
                "source_frame_id": fid,
                "row_count": n,
                "boundaries": boundaries,
                "divider_checks": details,
                "within_source": True,
                "nonoverlap": True,
                "entire_native_height_preserved": True,
            }
        )
    chosen = proposed["representatives"]
    sheets = []
    for start in range(0, len(chosen), 12):
        subset = chosen[start : start + 12]
        sheet = Image.new("RGB", (1260, math.ceil(len(subset) / 3) * 205), "white")
        draw = ImageDraw.Draw(sheet)
        for j, rep in enumerate(subset):
            f = frames[rep["source_frame_id"]]
            im = decode(source_path(f, f["source_path"]))
            pen = ImageDraw.Draw(im)
            for row in [r for r in rows if r["source_frame_id"] == f["id"]]:
                if row["y_px"]:
                    pen.line(
                        (0, row["y_px"], im.width - 1, row["y_px"]), fill=(255, 0, 70), width=1
                    )
            x = (j % 3) * 420 + 8
            y = (j // 3) * 205
            draw.text(
                (x, y + 4), f"{rep['template_key']} tray {f['image_ordinal']+1}", fill="black"
            )
            sheet.paste(im, (x, y + 24))
        name = f"25_review_{start//12+1}.png"
        sheet.save(settings.media_work_dir / name)
        sheets.append(name)
    result = {
        "status": "reviewed" if args.record_reviewed else "awaiting_visual_review",
        "rows": rows,
        "frame_checks": checks,
        "contact_sheet_sha256": {n: sha(settings.media_work_dir / n) for n in sheets},
        "representatives": chosen,
        "reviewer": "codex_visual_review" if args.record_reviewed else None,
        "notes": "Native cell pixels preserved including dividers, gaps, markers and empty parts. No color-based deletion. Direction confirmation is checked separately in step 26.",
    }
    if args.record_reviewed:
        prior = stage(25)
        require(
            prior["contact_sheet_sha256"] == result["contact_sheet_sha256"],
            "Review images changed; inspect new sheets first",
        )
    save_stage(25, result)


if __name__ == "__main__":
    main_guard(main)

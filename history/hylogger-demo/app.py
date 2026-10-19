from __future__ import annotations

import os
from pathlib import Path

from dash import Dash, Input, Output, dcc, html

from src.data import (
    load_depth_bins,
    load_holes,
    load_json,
    load_sample_groups,
    load_trays,
    summarize_tray,
    tray_record,
)
from src.figures import GROUP_COLORS, FALLBACK_GROUP_COLOR, build_tray_profile, group_style


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
HOLES = load_holes(DATA_DIR / "holes.csv")
TRAYS = load_trays(DATA_DIR / "05GJD001_trays.csv")
SAMPLES = load_sample_groups(DATA_DIR / "05GJD001_sample_groups.csv")
DEPTH_BINS = load_depth_bins(DATA_DIR / "05GJD001_depth_bins.csv")
SCAN_SUMMARY = SAMPLES[["mineral_group", "sample_id"]].groupby("mineral_group").size().sort_values(ascending=False)
METADATA = load_json(DATA_DIR / "05GJD001_scan_metadata.json")

HOLE = HOLES.iloc[0]
HOLE_ID = str(HOLE["hole_id"])
DEFAULT_TRAY_ID = str(TRAYS.iloc[0]["tray_id"])

app = Dash(__name__, title="HyLogger 05GJD001 Core Explorer")
server = app.server


def stat_card(label: str, value: str, detail: str | None = None) -> html.Div:
    children = [html.Span(label, className="stat-label"), html.Strong(value)]
    if detail:
        children.append(html.Small(detail))
    return html.Div(children, className="stat-card")


def tray_option_label(row) -> str:
    return f"Tray {row.tray_id} · {row.depth_from_m:.3f}–{row.depth_to_m:.3f} m"


def tray_range_text(tray_id: str) -> str:
    row = tray_record(TRAYS, tray_id)
    return f"Recorded depth {float(row['depth_from_m']):.3f}–{float(row['depth_to_m']):.3f} m"


def core_image_panel(tray_id: str) -> html.Div:
    tray = tray_record(TRAYS, tray_id)
    image_relpath = str(tray["image_relpath"])
    image_path = PROJECT_ROOT / "assets" / image_relpath if image_relpath else None
    depth_text = f"{float(tray['depth_from_m']):.3f}–{float(tray['depth_to_m']):.3f} m"

    if str(tray["image_status"]) == "available" and image_path and image_path.is_file():
        return html.Figure(
            [
                html.Img(
                    src=app.get_asset_url(image_relpath),
                    alt=f"05GJD001 tray {tray_id}, recorded depth {depth_text}",
                    draggable=False,
                ),
                html.Figcaption(
                    [
                        html.Strong(f"05GJD001 · tray {tray_id}"),
                        html.Span(depth_text),
                        html.Small("Resized from the supplied source photograph; one tray image is loaded at a time."),
                    ]
                ),
            ],
            className="core-figure",
        )

    return html.Div(
        [
            html.Span("IMAGE NOT AVAILABLE", className="slot-kicker"),
            html.Strong(f"Tray {tray_id}"),
            html.P(f"The image field is retained for {depth_text}; no replacement image is inferred."),
        ],
        className="image-placeholder",
    )


def tray_summary_panel(tray_id: str) -> html.Div:
    summary = summarize_tray(TRAYS, SAMPLES, DEPTH_BINS, tray_id)
    return html.Div(
        [
            stat_card("Tray", summary["tray_id"]),
            stat_card(
                "Depth range",
                f'{summary["depth_from_m"]:.3f}–{summary["depth_to_m"]:.3f} m',
            ),
            stat_card("Scan samples", f'{summary["sample_count"]:,}'),
            stat_card("Displayed 0.1 m bins", f'{summary["bin_count"]:,}'),
            stat_card(
                "Most frequent NIR group",
                summary["top_group"],
                f'{summary["top_group_share_pct"]:.1f}% of this tray’s samples',
            ),
            stat_card("Image status", summary["image_status"].title()),
        ],
        className="tray-stat-grid",
    )


def group_legend() -> html.Div:
    total = int(SCAN_SUMMARY.sum())
    keys = []
    for group, count in SCAN_SUMMARY.items():
        style = group_style(group)
        class_names = "group-swatch"
        if group in {"NO RESULT", "INVALID", "NOTAROK"}:
            class_names += f" {group.lower().replace(' ', '-')}"
        keys.append(
            html.Div(
                [
                    html.Span(
                        className=class_names,
                        style={"backgroundColor": GROUP_COLORS.get(group, FALLBACK_GROUP_COLOR)},
                    ),
                    html.Div(
                        [
                            html.Strong(str(group)),
                            html.Small(f"{int(count):,} samples · {count / total * 100:.1f}%"),
                        ]
                    ),
                ],
                className="group-key",
            )
        )
    return html.Div(keys, className="group-legend")


def metadata_grid() -> html.Div:
    items = [
        ("Source bundle", str(METADATA["source_bundle_id"])),
        ("Hole ID", HOLE_ID),
        ("Recorded depth", f'{METADATA["depth_min_m"]:.3f}–{METADATA["depth_max_m"]:.3f} m'),
        ("NIR", f'{METADATA["nir_channels"]} channels · {METADATA["nir_wavelength_min_nm"]:.0f}–{METADATA["nir_wavelength_max_nm"]:.0f} nm'),
        ("TIR", f'{METADATA["tir_channels"]} channels · {METADATA["tir_wavelength_min_nm"]:.0f}–{METADATA["tir_wavelength_max_nm"]:.0f} nm'),
        ("NIR group field", str(METADATA["group_algorithm_field"])),
        ("Display bin", f'{METADATA["depth_bin_size_m"]:.1f} m'),
        ("Confidence", "Not supplied · not inferred"),
    ]
    return html.Div(
        [html.Div([html.Span(label), html.Strong(value)], className="metadata-item") for label, value in items],
        className="metadata-grid",
    )


tray_options = [
    {"label": tray_option_label(row), "value": str(row.tray_id)}
    for row in TRAYS.itertuples(index=False)
]

app.layout = html.Div(
    [
        html.Header(
            [
                html.Div(
                    [
                        html.P("SUPPLIED SOURCE PACKAGE · 05GJD001", className="eyebrow"),
                        html.H1("HyLogger 05GJD001 Core Explorer"),
                        html.P(
                            "Browse the supplied drill-core photographs and the NIR mineral-group output at their recorded absolute depths.",
                            className="lede",
                        ),
                    ],
                    className="hero-copy",
                ),
                html.Div(
                    [
                        html.Strong("Actual supplied scan package"),
                        html.Span("Coordinates and confidence values were not supplied. They are left blank and are not inferred."),
                    ],
                    className="data-notice",
                ),
            ],
            className="hero",
        ),
        html.Main(
            [
                html.Section(
                    [
                        html.Div(
                            [
                                html.P("HOLE RECORD", className="section-index"),
                                html.H2("One supplied drill hole — no invented locations"),
                            ],
                            className="section-heading",
                        ),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        stat_card("Hole", HOLE_ID),
                                        stat_card("Recorded depth", f'{METADATA["depth_min_m"]:.3f}–{METADATA["depth_max_m"]:.3f} m'),
                                        stat_card("Scan samples", f'{METADATA["sample_count"]:,}'),
                                        stat_card("Core trays", str(METADATA["tray_count"])),
                                    ],
                                    className="hole-stat-grid",
                                ),
                                html.Div(
                                    [
                                        html.Span("LOCATION SLOT", className="slot-kicker"),
                                        html.H3("Coordinates not supplied"),
                                        html.Div(
                                            [
                                                html.Div([html.Span("Latitude"), html.Strong("—")]),
                                                html.Div([html.Span("Longitude"), html.Strong("—")]),
                                            ],
                                            className="coordinate-grid",
                                        ),
                                        html.P(
                                            "The fields remain empty in data/holes.csv for later authoritative coordinates. No map or approximate location is rendered.",
                                        ),
                                    ],
                                    className="location-placeholder",
                                ),
                            ],
                            className="record-grid",
                        ),
                    ],
                    className="record-section",
                ),
                html.Section(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.P("STEP 01", className="section-index"),
                                        html.H2("Choose a recorded core tray"),
                                    ]
                                ),
                                html.Span("33 source photographs", className="quiet-chip"),
                            ],
                            className="section-heading row",
                        ),
                        dcc.Dropdown(
                            id="tray-selector",
                            options=tray_options,
                            value=DEFAULT_TRAY_ID,
                            clearable=False,
                            searchable=True,
                            className="tray-selector",
                        ),
                        html.P(id="selected-tray-range", children=tray_range_text(DEFAULT_TRAY_ID), className="selected-range"),
                    ],
                    className="tray-control",
                ),
                html.Div(
                    [
                        html.Section(
                            [
                                html.Div(
                                    [
                                        html.P("CORE PHOTOGRAPH", className="section-index"),
                                        html.H2("Current tray image"),
                                    ],
                                    className="section-heading",
                                ),
                                dcc.Loading(
                                    html.Div(id="core-image-panel", children=core_image_panel(DEFAULT_TRAY_ID)),
                                    type="circle",
                                    color="#197986",
                                ),
                                html.P(
                                    "Only the selected web-sized photograph is added to the page. Missing or unreadable files produce an explicit placeholder.",
                                    className="loading-note",
                                ),
                            ],
                            className="panel image-panel",
                        ),
                        html.Section(
                            [
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.P("STEP 02", className="section-index"),
                                                html.H2("Read the actual NIR group profile"),
                                            ]
                                        ),
                                        html.Span(f"Tray {DEFAULT_TRAY_ID}", id="tray-chip", className="tray-chip"),
                                    ],
                                    className="section-heading row",
                                ),
                                html.P(
                                    "Depth increases downward using the recorded absolute depth. Hover a strip for the source group and sample counts.",
                                    className="section-intro",
                                ),
                                html.Div(id="tray-summary", children=tray_summary_panel(DEFAULT_TRAY_ID)),
                                html.Div(
                                    dcc.Graph(
                                        id="depth-profile",
                                        figure=build_tray_profile(DEPTH_BINS, DEFAULT_TRAY_ID),
                                        config={"displaylogo": False, "displayModeBar": False, "responsive": True},
                                        style={"height": "760px"},
                                    ),
                                    className="profile-frame",
                                ),
                            ],
                            className="panel profile-panel",
                        ),
                    ],
                    className="workspace-grid",
                ),
                html.Section(
                    [
                        html.Div(
                            [
                                html.P("HOW TO READ THIS", className="section-index"),
                                html.H2("Observed group output, not invented confidence"),
                            ],
                            className="section-heading",
                        ),
                        html.Div(
                            [
                                html.P(
                                    [
                                        html.Strong("Each 0.1 m strip "),
                                        "shows the most frequent value from the real ",
                                        html.Code("Grp1 sTSAS"),
                                        " samples inside that depth bin.",
                                    ]
                                ),
                                html.P(
                                    [
                                        html.Strong("Within-bin share is a count, not confidence. "),
                                        "The package has no confidence field used by this page, so none is created.",
                                    ]
                                ),
                                html.P(
                                    [
                                        html.Strong("NO RESULT, INVALID, and NOTAROK remain visible. "),
                                        "They are never replaced with a mineral label.",
                                    ]
                                ),
                            ],
                            className="method-callout",
                        ),
                        group_legend(),
                    ],
                    className="method-section",
                ),
                html.Section(
                    [
                        html.Div(
                            [
                                html.P("SCAN METADATA", className="section-index"),
                                html.H2("Parameters extracted with pytsg"),
                            ],
                            className="section-heading",
                        ),
                        metadata_grid(),
                        html.P(str(METADATA["provenance_note"]), className="provenance-note"),
                    ],
                    className="metadata-section",
                ),
            ],
            className="page-shell",
        ),
        html.Footer(
            "Local 05GJD001 explorer · supplied package only · no inferred location or confidence",
            className="footer",
        ),
    ]
)


@app.callback(
    Output("selected-tray-range", "children"),
    Output("core-image-panel", "children"),
    Output("tray-summary", "children"),
    Output("depth-profile", "figure"),
    Output("tray-chip", "children"),
    Input("tray-selector", "value"),
)
def update_tray(tray_id: str):
    normalized = str(tray_id or DEFAULT_TRAY_ID).zfill(4)
    return (
        tray_range_text(normalized),
        core_image_panel(normalized),
        tray_summary_panel(normalized),
        build_tray_profile(DEPTH_BINS, normalized),
        f"Tray {normalized}",
    )


if __name__ == "__main__":
    host = os.environ.get("HYLOGGER_HOST", "127.0.0.1")
    port = int(os.environ.get("HYLOGGER_PORT", "8050"))
    app.run(host=host, port=port, debug=False)

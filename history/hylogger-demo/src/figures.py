"""Plotly figures derived only from the extracted 05GJD001 scan groups."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .data import tray_bins


GROUP_COLORS = {
    "CHLORITE": "#3f8461",
    "CARBONATE": "#3f91a8",
    "DARK-MICA": "#765443",
    "WHITE-MICA": "#d0ae4d",
    "AMPHIBOLE": "#7966a5",
    "OTHER-ALOH": "#b96f97",
    "SULPHATE": "#d77d3c",
    "EPIDOTE": "#4fa7a2",
    "SMECTITE": "#a98955",
    "TOURMALINE": "#514d80",
    "KAOLIN": "#d7c178",
    "SERPENTINE": "#316f5c",
    "NO RESULT": "#303941",
    "INVALID": "#9ba3aa",
    "NOTAROK": "#5d6871",
}
FALLBACK_GROUP_COLOR = "#65757d"


def group_style(group: str) -> dict[str, object]:
    label = str(group)
    if label == "NO RESULT":
        return {"color": GROUP_COLORS[label], "pattern": "/", "pattern_color": "#d5dade"}
    if label == "INVALID":
        return {"color": GROUP_COLORS[label], "pattern": "x", "pattern_color": "#4f5a62"}
    if label == "NOTAROK":
        return {"color": GROUP_COLORS[label], "pattern": ".", "pattern_color": "#e0e4e6"}
    return {"color": GROUP_COLORS.get(label, FALLBACK_GROUP_COLOR), "pattern": "", "pattern_color": ""}


def build_tray_profile(depth_bins: pd.DataFrame, tray_id: str) -> go.Figure:
    rows = tray_bins(depth_bins, tray_id)
    depth_from = float(rows["depth_from_m"].min())
    depth_to = float(rows["depth_to_m"].max())
    figure = go.Figure()

    for group, group_rows in rows.groupby("mineral_group", sort=False):
        style = group_style(group)
        marker: dict[str, object] = {
            "color": style["color"],
            "line": {"color": "#ffffff", "width": 0.35},
        }
        if style["pattern"]:
            marker["pattern"] = {
                "shape": style["pattern"],
                "fgcolor": style["pattern_color"],
                "bgcolor": style["color"],
                "solidity": 0.2,
                "size": 7,
            }

        thickness = group_rows["depth_to_m"] - group_rows["depth_from_m"]
        customdata = group_rows[
            [
                "depth_from_m",
                "depth_to_m",
                "mineral_group",
                "sample_count",
                "dominant_sample_count",
                "dominant_share_pct",
                "algorithm_field",
            ]
        ].to_numpy()
        figure.add_trace(
            go.Bar(
                x=["NIR group"] * len(group_rows),
                y=thickness,
                base=group_rows["depth_from_m"],
                width=0.72,
                marker=marker,
                customdata=customdata,
                hovertemplate=(
                    "<b>Depth %{customdata[0]:.3f}–%{customdata[1]:.3f} m</b><br>"
                    "Dominant NIR group: %{customdata[2]}<br>"
                    "Samples in bin: %{customdata[3]}<br>"
                    "Samples with this group: %{customdata[4]}<br>"
                    "Within-bin share: %{customdata[5]:.1f}%<br>"
                    "Source field: %{customdata[6]}<extra></extra>"
                ),
                name=str(group),
                showlegend=False,
            )
        )

    figure.update_layout(
        barmode="overlay",
        bargap=0,
        height=760,
        margin={"l": 82, "r": 30, "t": 24, "b": 26},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f5f7f5",
        hoverlabel={"bgcolor": "#102c37", "font": {"color": "white", "size": 13}},
        uirevision=f"tray-{str(tray_id).zfill(4)}",
    )
    figure.update_xaxes(
        showgrid=False,
        zeroline=False,
        showticklabels=False,
        fixedrange=True,
        range=[-0.64, 0.64],
    )
    figure.update_yaxes(
        title="Recorded depth (m)",
        autorange=False,
        range=[depth_to, depth_from],
        dtick=0.5,
        tickformat=".1f",
        showgrid=True,
        gridcolor="#dce3e1",
        zeroline=False,
        fixedrange=True,
    )
    return figure

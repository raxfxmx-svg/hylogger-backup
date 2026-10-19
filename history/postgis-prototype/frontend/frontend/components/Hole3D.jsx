"use client";

// The 3D view, drawn with deck.gl in an orbit camera (drag to rotate, scroll to zoom).
//
// Coordinates are plain metres, not longitude/latitude: we pick the middle of the
// selected holes as the origin, then place everything east/north/down from there.
// That keeps the maths obvious and avoids fighting a map projection underground.

import { useMemo, useState } from "react";
import DeckGL, { COORDINATE_SYSTEM, OrbitView, ColumnLayer, ScatterplotLayer } from "deck.gl";
import { ANOMALY_COLOUR, mineralColour, toRgb } from "@/config";

const METRES_PER_DEGREE_LAT = 110540;

export default function Hole3D({ traces = [], verticalExaggeration = 25, colourBy = "mineral" }) {
  const [hovered, setHovered] = useState(null);
  const [selected, setSelected] = useState(null);

  const { segments, collars, anomalies, view } = useMemo(
    () => buildScene(traces, verticalExaggeration, colourBy),
    [traces, verticalExaggeration, colourBy]
  );

  if (!traces.length) {
    return <p className="empty">Choose one or more holes to see them in 3D.</p>;
  }

  const layers = [
    new ColumnLayer({
      id: "hole-sections",
      data: segments,
      coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      diskResolution: 12,
      // Keep the demo cylinder selectable at every camera distance. A real
      // borehole diameter would be sub-pixel when the full depth is visible.
      radius: 14,
      radiusUnits: "pixels",
      radiusMinPixels: 12,
      radiusMaxPixels: 22,
      extruded: true,
      stroked: true,
      wireframe: false,
      getPosition: (segment) => segment.position,
      getElevation: (segment) => segment.elevation,
      getFillColor: (segment) =>
        segment === selected ? [255, 179, 71] : segment.colour,
      getLineColor: [8, 45, 45, 220],
      lineWidthMinPixels: 1,
      pickable: true,
      autoHighlight: true,
      highlightColor: [255, 255, 255, 90],
      onHover: (info) => setHovered(info.object ? info : null),
      onClick: (info) => setSelected(info.object?.imageUrl ? info.object : null),
      updateTriggers: {
        getFillColor: [selected],
      },
    }),
    new ScatterplotLayer({
      id: "collars",
      data: collars,
      coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      getPosition: (collar) => collar.position,
      getFillColor: [79, 209, 197],
      radiusUnits: "pixels",
      getRadius: 5,
      pickable: true,
      onHover: (info) => setHovered(info.object ? info : null),
    }),
    new ScatterplotLayer({
      id: "anomaly-points",
      data: anomalies,
      coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      getPosition: (point) => point.position,
      getFillColor: toRgb(ANOMALY_COLOUR),
      radiusUnits: "pixels",
      getRadius: 4,
      pickable: true,
      onHover: (info) => setHovered(info.object ? info : null),
    }),
  ];

  return (
    <>
      <DeckGL
        views={new OrbitView({ orbitAxis: "Z" })}
        initialViewState={view}
        controller={true}
        layers={layers}
        style={{ position: "absolute", inset: 0 }}
      />
      {hovered?.object && (
        <div className="tooltip" style={{ left: hovered.x + 14, top: hovered.y + 14 }}>
          {hovered.object.holeId}
          {hovered.object.depth != null && <> · {hovered.object.depth.toFixed(0)} m</>}
          {hovered.object.mineral && <><br />{hovered.object.mineral}</>}
        </div>
      )}
      {selected?.imageUrl && (
        <div className="core-image-panel">
          <div className="core-image-heading">
            <div>
              <strong className="mono">{selected.holeId}</strong>
              <div className="hint">
                {selected.depth.toFixed(2)}–{selected.depthTo.toFixed(2)} m
              </div>
            </div>
            <button className="action" onClick={() => setSelected(null)}>Close</button>
          </div>
          <img
            src={selected.imageUrl}
            alt={`Core thumbnail for ${selected.holeId} at ${selected.depth} metres`}
          />
          <p className="hint">Thumbnail-derived image from the registered PostGIS section.</p>
        </div>
      )}
    </>
  );
}

function buildScene(traces, exaggeration, colourBy) {
  const empty = { segments: [], collars: [], anomalies: [], view: defaultView() };
  if (!traces.length) return empty;

  // origin = middle of the selected holes
  const originLat = average(traces.map((t) => t.latitude));
  const originLon = average(traces.map((t) => t.longitude));
  const metresPerDegreeLon =
    METRES_PER_DEGREE_LAT * Math.cos((originLat * Math.PI) / 180);
  const allDepths = traces.flatMap((trace) => trace.points.map((point) => point.tvd_m));
  const depthOrigin = (Math.min(...allDepths) + Math.max(...allDepths)) / 2;

  const segments = [];
  const collars = [];
  const anomalies = [];
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;

  traces.forEach((trace) => {
    const collarX = (trace.longitude - originLon) * metresPerDegreeLon;
    const collarY = (trace.latitude - originLat) * METRES_PER_DEGREE_LAT;
    const points = trace.points.map((point) => [
      collarX + point.east_m,
      collarY + point.north_m,
      -(point.tvd_m - depthOrigin) * exaggeration, // centred near zero; negative = down
    ]);

    points.forEach(([x, y, z]) => {
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
      minZ = Math.min(minZ, z);
      maxZ = Math.max(maxZ, z);
    });

    if (points.length) {
      // The current release starts at the first imaged interval (around 150 m),
      // so mark and frame that point instead of an off-screen collar at 0 m.
      collars.push({
        position: points[0],
        holeId: trace.hole_id,
        depth: trace.points[0].depth_m,
      });
    }

    for (let i = 0; i < points.length - 1; i += 1) {
      const point = trace.points[i];
      const lowerZ = Math.min(points[i][2], points[i + 1][2]);
      const upperZ = Math.max(points[i][2], points[i + 1][2]);
      segments.push({
        position: [points[i][0], points[i][1], lowerZ],
        elevation: Math.max(upperZ - lowerZ, 0.25),
        colour:
          colourBy === "anomaly"
            ? anomalyColour(point.anomaly_score)
            : point.mineral
              ? toRgb(mineralColour(point.mineral))
              : [79, 209, 197],
        holeId: trace.hole_id,
        depth: point.depth_m,
        mineral: point.mineral,
        depthTo: point.depth_to_m ?? trace.points[i + 1].depth_m,
        imageUrl: point.image_url,
        imageQuality: point.image_quality,
      });

      if (point.is_anomaly) {
        anomalies.push({
          position: points[i],
          holeId: trace.hole_id,
          depth: point.depth_m,
          mineral: point.mineral,
        });
      }
    }
  });

  if (!segments.length || !Number.isFinite(minZ)) return empty;

  // Frame only the interval that actually has section images. The first current
  // image is around 150 m, so including the empty 0–150 m span made the useful
  // part appear as a dot at the edge of the old camera.
  const centreX = (minX + maxX) / 2;
  const centreY = (minY + maxY) / 2;
  const centreZ = (minZ + maxZ) / 2;
  const horizontalSpan = Math.max(maxX - minX, maxY - minY);
  const verticalSpan = maxZ - minZ;
  const halfSize = Math.max(horizontalSpan / 2, verticalSpan / 2, 20);

  return {
    segments,
    collars,
    anomalies,
    view: {
      ...defaultView(),
      target: [centreX, centreY, centreZ],
      // Leave enough camera distance for the cylinder's near face. The user can
      // zoom in after the complete available interval is visible.
      zoom: Math.min(-0.75, Math.log2(120 / halfSize)),
    },
  };
}

/** Cool grey when ordinary, amber when odd. */
function anomalyColour(score = 0) {
  const amber = toRgb(ANOMALY_COLOUR);
  const grey = [90, 102, 114];
  return grey.map((value, index) => Math.round(value + (amber[index] - value) * score));
}

const defaultView = () => ({
  target: [0, 0, 0],
  zoom: -2,
  rotationX: 60,
  rotationOrbit: 30,
  minZoom: -12,
  maxZoom: 12,
});

const average = (values) => values.reduce((total, value) => total + value, 0) / values.length;

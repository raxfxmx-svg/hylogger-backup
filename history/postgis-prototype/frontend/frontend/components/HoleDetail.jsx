"use client";

// The right-hand panel: what this hole is, its mineral log, and what's near it.

import { useEffect, useState } from "react";
import Link from "next/link";
import { getHole, getMeasurements, getNearby } from "@/lib/api";
import { ANOMALY_COLOUR, LOW_CONFIDENCE_COLOUR } from "@/config";
import StripLog from "./StripLog";

export default function HoleDetail({ holeId, onSelect }) {
  const [hole, setHole] = useState(null);
  const [measurements, setMeasurements] = useState([]);
  const [nearby, setNearby] = useState([]);
  const [selectedImage, setSelectedImage] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!holeId) return;
    setError(null);
    setHole(null);
    setSelectedImage(null);

    Promise.all([
      getHole(holeId),
      getMeasurements(holeId),
      getNearby(holeId, 50),
    ])
      .then(([holeData, measurementData, nearbyData]) => {
        setHole(holeData);
        setMeasurements(measurementData);
        setNearby(nearbyData);
      })
      .catch((err) => setError(err.message));
  }, [holeId]);

  if (!holeId) {
    return (
      <aside className="detail">
        <p className="empty">
          Pick a hole on the map or in the list.
          <br />
          Its mineral log appears here.
        </p>
      </aside>
    );
  }

  if (error) {
    return <aside className="detail"><div className="error">{error}</div></aside>;
  }

  if (!hole) {
    return <aside className="detail"><p className="hint">Loading {holeId}…</p></aside>;
  }

  const lowConfidence = measurements.filter((m) => m.confidence < 0.5).length;

  return (
    <aside className="detail">
      <h2 style={{ margin: "0 0 2px", fontSize: 20 }} className="mono">{hole.hole_id}</h2>
      <p style={{ margin: "0 0 16px", color: "var(--text-dim)" }}>{hole.hole_name}</p>

      <table className="facts">
        <tbody>
          <tr><td>Length</td><td>{fmt(hole.borehole_length_m)} m</td></tr>
          <tr><td>Data source</td><td>PostGIS</td></tr>
          <tr><td>Latitude</td><td>{hole.latitude?.toFixed(5)}</td></tr>
          <tr><td>Longitude</td><td>{hole.longitude?.toFixed(5)}</td></tr>
          <tr><td>Azimuth</td><td>{fmtDirection(hole.azimuth_deg, hole.orientation_status)}</td></tr>
          <tr><td>Inclination</td><td>{fmtDirection(hole.inclination_deg, hole.orientation_status)}</td></tr>
          <tr><td>Core sections</td><td>{hole.measurement_count}</td></tr>
          <tr><td>Operator</td><td>{hole.operator || "–"}</td></tr>
          <tr>
            <td>Flagged</td>
            <td>
              {hole.anomaly_count > 0
                ? <span className="badge warn">{hole.anomaly_count} unusual</span>
                : <span className="badge">none</span>}
            </td>
          </tr>
        </tbody>
      </table>

      <p className="section-title">Mineral log</p>
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        <StripLog
          measurements={measurements}
          height={420}
          onSelectInterval={setSelectedImage}
        />
        <Legend measurements={measurements} lowConfidence={lowConfidence} />
      </div>

      {selectedImage && (
        <CoreImagePreview section={selectedImage} onClose={() => setSelectedImage(null)} />
      )}

      <p className="section-title" style={{ marginTop: 22 }}>Nearest holes</p>
      {nearby.length === 0 ? (
        <p className="hint">Nothing else within 50 km.</p>
      ) : (
        <div>
          {nearby.slice(0, 6).map((other) => (
            <button
              key={other.hole_id}
              className="hole-row"
              onClick={() => onSelect?.(other.hole_id)}
            >
              <span className="id">{other.hole_id}</span>
              <span className="name">{other.hole_name}</span>
              <span className="len">{other.distance_km.toFixed(1)} km</span>
            </button>
          ))}
          <p style={{ marginTop: 12 }}>
            <Link href={`/compare?a=${hole.hole_id}&b=${nearby[0].hole_id}`}>
              Compare with {nearby[0].hole_id} →
            </Link>
          </p>
        </div>
      )}
    </aside>
  );
}

function CoreImagePreview({ section, onClose }) {
  return (
    <div className="core-image-card">
      <div className="core-image-heading">
        <span className="mono">
          {section.depth_from_m.toFixed(2)}–{section.depth_to_m.toFixed(2)} m
        </span>
        <button className="action" onClick={onClose}>Close</button>
      </div>
      <img
        src={section.image_url}
        alt={`Core thumbnail from ${section.depth_from_m} to ${section.depth_to_m} metres`}
      />
      <p className="hint">Thumbnail-derived image · section {section.section_index}</p>
    </div>
  );
}

function Legend({ measurements, lowConfidence }) {
  const present = [...new Map(
    measurements
      .filter((m) => m.mineral_group && m.mineral_colour && m.confidence >= 0.5)
      .map((m) => [m.mineral_group, m.mineral_colour])
  ).entries()];

  return (
    <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
      {present.map(([group, colour]) => (
        <div className="legend-item" key={group}>
          <span
            className="legend-swatch"
            style={{ background: colour }}
          />
          {group}
        </div>
      ))}
      <div className="legend-item" style={{ marginTop: 10 }}>
        <span className="legend-swatch" style={{ background: LOW_CONFIDENCE_COLOUR }} />
        low confidence ({lowConfidence})
      </div>
      <div className="legend-item">
        <span className="legend-swatch" style={{ background: ANOMALY_COLOUR }} />
        unusual reading
      </div>
    </div>
  );
}

const fmt = (value) => (value == null ? "–" : Number(value).toFixed(1));
const fmtDirection = (value, status) =>
  status === "reported" && value != null ? `${Number(value).toFixed(1)}°` : "–";

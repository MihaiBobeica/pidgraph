"use client";

import { useEffect, useMemo, useState } from "react";
import { BAND_COLOUR, confidenceBand, trace, type Snapshot } from "@/lib/graph";

// The drawing is the interface. Because extraction records the true bounding box of every symbol
// in drawing coordinates, hotspots sit exactly on the geometry rather than approximating it, and
// the abstract view can place nodes at their real positions -- which looks like a P&ID because it
// is the P&ID.
export default function Page() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [showConfidence, setShowConfidence] = useState(true);
  const [tracing, setTracing] = useState(false);

  useEffect(() => {
    fetch("/api/snapshot")
      .then((r) => r.json())
      .then(setSnapshot)
      .catch(() => setSnapshot(null));
  }, []);

  const nodes = useMemo(
    () =>
      (snapshot?.nodes ?? []).filter(
        // A node without a finite box cannot be drawn; letting it through puts NaN into svg
        // attributes and blanks the layer without an error.
        (n) =>
          n.page === page &&
          Array.isArray(n.bbox) &&
          n.bbox.length === 4 &&
          n.bbox.every((v) => Number.isFinite(v)),
      ),
    [snapshot, page],
  );
  const keys = useMemo(() => new Set(nodes.map((n) => n.stable_key)), [nodes]);
  const edges = useMemo(
    () => (snapshot?.edges ?? []).filter((e) => keys.has(e.source) && keys.has(e.target)),
    [snapshot, keys],
  );

  // Flow tracing: what an engineer actually wants from a P&ID, and only possible because
  // connectivity was recovered properly rather than approximated.
  const traced = useMemo(() => {
    if (!tracing || !selected) return null;
    return trace(edges, selected);
  }, [tracing, selected, edges]);

  const byKey = useMemo(() => new Map(nodes.map((n) => [n.stable_key, n])), [nodes]);
  const active = selected ? (byKey.get(selected) ?? null) : null;

  if (!snapshot) return <div className="empty">Loading...</div>;
  if (!snapshot.nodes.length) {
    return (
      <div className="empty">
        No graph available. Run <code>pidgraph check</code> to produce one.
      </div>
    );
  }

  const sheet = snapshot.pages[page] ?? { index: 0, width: 1224, height: 792 };
  const counts = {
    total: nodes.length,
    instruments: nodes.filter((n) => n.kind === "instrument").length,
    low: nodes.filter((n) => confidenceBand(n.confidence) === "low").length,
  };

  return (
    <div className="app">
      <header>
        <h1>pidgraph</h1>
        <span className="meta">
          {snapshot.nodes.length} nodes &middot; {snapshot.edges.length} edges &middot; source:{" "}
          {snapshot.source}
        </span>
        <div className="controls">
          {snapshot.pages.map((p) => (
            <button key={p.index} data-on={p.index === page} onClick={() => setPage(p.index)}>
              sheet {p.index + 1}
            </button>
          ))}
          <button data-on={showConfidence} onClick={() => setShowConfidence((v) => !v)}>
            confidence
          </button>
          <button data-on={tracing} onClick={() => setTracing((v) => !v)}>
            trace
          </button>
        </div>
      </header>

      <div className="panes">
        <div className="stage">
          {/* One transformed surface rather than one element per hotspot: several hundred
              individually positioned overlays repaint every frame and collapse the frame rate. */}
          <svg viewBox={`0 0 ${sheet.width} ${sheet.height}`} preserveAspectRatio="xMidYMid meet">
            <rect width={sheet.width} height={sheet.height} fill="#070b0f" />
            {edges.map((e, i) => {
              const a = byKey.get(e.source);
              const b = byKey.get(e.target);
              if (!a || !b) return null;
              const on = traced ? traced.has(e.source) && traced.has(e.target) : false;
              const stroke = on
                ? "#38bdf8"
                : showConfidence
                  ? BAND_COLOUR[confidenceBand(e.confidence)]
                  : "#33465a";
              return (
                <line
                  key={i}
                  x1={(a.bbox[0] + a.bbox[2]) / 2}
                  y1={(a.bbox[1] + a.bbox[3]) / 2}
                  x2={(b.bbox[0] + b.bbox[2]) / 2}
                  y2={(b.bbox[1] + b.bbox[3]) / 2}
                  stroke={stroke}
                  strokeWidth={on ? 2.4 : 0.9}
                  strokeOpacity={traced && !on ? 0.15 : 0.85}
                  strokeDasharray={e.style === "dashed" ? "4 3" : undefined}
                />
              );
            })}
            {/* Largest first, so the smallest symbol is painted last and wins the click: label
                boxes sit inside equipment boxes, and otherwise every click hits the container. */}
            {[...nodes]
              .sort(
                (p, q) =>
                  (q.bbox[2] - q.bbox[0]) * (q.bbox[3] - q.bbox[1]) -
                  (p.bbox[2] - p.bbox[0]) * (p.bbox[3] - p.bbox[1]),
              )
              .map((n) => {
                const depth = traced?.get(n.stable_key);
                const dim = traced !== null && depth === undefined;
                const colour =
                  depth === 0
                    ? "#38bdf8"
                    : showConfidence
                      ? BAND_COLOUR[confidenceBand(n.confidence)]
                      : n.kind === "instrument"
                        ? "#38bdf8"
                        : "#7c8ea0";
                return (
                  <rect
                    key={n.stable_key}
                    className="node"
                    x={n.bbox[0]}
                    y={n.bbox[1]}
                    width={Math.max(n.bbox[2] - n.bbox[0], 2)}
                    height={Math.max(n.bbox[3] - n.bbox[1], 2)}
                    fill={n.stable_key === selected ? colour : "none"}
                    fillOpacity={0.25}
                    stroke={colour}
                    strokeWidth={n.stable_key === selected ? 2 : 0.8}
                    strokeOpacity={dim ? 0.12 : 1}
                    onClick={() => setSelected(n.stable_key)}
                  />
                );
              })}
          </svg>
        </div>

        <aside className="side">
          <h2>Sheet {page + 1}</h2>
          <div className="row">
            <span className="k">nodes</span>
            <span>{counts.total}</span>
          </div>
          <div className="row">
            <span className="k">instruments</span>
            <span>{counts.instruments}</span>
          </div>
          <div className="row">
            <span className="k">edges</span>
            <span>{edges.length}</span>
          </div>
          <div className="row">
            <span className="k">low confidence</span>
            <span>{counts.low}</span>
          </div>

          {showConfidence && (
            <>
              <h2>Confidence</h2>
              <p style={{ color: "var(--muted)", fontSize: 12, margin: "4px 0" }}>
                Shading shows how strongly each claim is supported. Weak claims are shown rather
                than hidden, which is what makes the rest of the graph believable.
              </p>
              <div className="legend">
                {(["high", "medium", "low"] as const).map((band) => (
                  <span key={band}>
                    <i className="swatch" style={{ background: BAND_COLOUR[band] }} />
                    {band}
                  </span>
                ))}
              </div>
            </>
          )}

          <h2>Selection</h2>
          {active ? (
            <>
              <div className="row">
                <span className="k">key</span>
                <span className="mono">{active.stable_key.slice(0, 16)}</span>
              </div>
              <div className="row">
                <span className="k">kind</span>
                <span>{active.kind}</span>
              </div>
              <div className="row">
                <span className="k">class</span>
                <span>{active.dexpi_class ?? "unresolved"}</span>
              </div>
              <div className="row">
                <span className="k">tag</span>
                <span className="tag">{active.tag ?? "-"}</span>
              </div>
              <div className="row">
                <span className="k">confidence</span>
                <span>{(active.confidence * 100).toFixed(0)}%</span>
              </div>
              {traced && (
                <div className="row">
                  <span className="k">reachable</span>
                  <span>{traced.size} nodes</span>
                </div>
              )}
            </>
          ) : (
            <p style={{ color: "var(--muted)", fontSize: 12 }}>
              Select a symbol on the drawing. With <em>trace</em> enabled the connected path is
              highlighted and everything else dimmed.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}

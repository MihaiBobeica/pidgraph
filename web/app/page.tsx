"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  BAND_COLOUR,
  SEVERITY_COLOUR,
  confidenceBand,
  trace,
  type Finding,
  type Node,
  type Snapshot,
} from "@/lib/graph";

// The drawing is the interface. Extraction records the true bounding box of every symbol in
// drawing coordinates, so hotspots sit exactly on the geometry -- and the viewport is a camera
// over the real sheet: wheel to zoom, drag to pan, click to inspect. Words are a last resort.
type View = { x: number; y: number; w: number; h: number };

export default function Page() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [failed, setFailed] = useState(false);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [tracing, setTracing] = useState(false);
  const [showConfidence, setShowConfidence] = useState(true);
  const [query, setQuery] = useState("");
  const [view, setView] = useState<View | null>(null);
  const [touched, setTouched] = useState(false);
  const [openFinding, setOpenFinding] = useState<number | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const [panning, setPanning] = useState(false);

  const load = () => {
    setFailed(false);
    fetch("/api/snapshot")
      .then((r) => r.json())
      .then(setSnapshot)
      .catch(() => setFailed(true));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  const nodes = useMemo(
    () =>
      (snapshot?.nodes ?? []).filter(
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
  const byKey = useMemo(() => new Map(nodes.map((n) => [n.stable_key, n])), [nodes]);
  const active = selected ? (byKey.get(selected) ?? null) : null;
  const traced = useMemo(
    () => (tracing && selected ? trace(edges, selected) : null),
    [tracing, selected, edges],
  );

  // Sheets are looked up by their index field: the pages array only holds sheets that have
  // nodes, so array position and page index diverge whenever a sheet is empty.
  const sheet = snapshot?.pages.find((p) => p.index === page) ?? {
    index: 0,
    width: 1224,
    height: 792,
  };
  const fit = useMemo<View>(
    () => ({ x: 0, y: 0, w: sheet.width, h: sheet.height }),
    [sheet.width, sheet.height],
  );
  const box = view ?? fit;

  // Search across every sheet, by tag first and kind second.
  const hits = useMemo(() => {
    const q = query.trim().toUpperCase();
    if (!q || !snapshot) return [];
    return snapshot.nodes
      .filter((n) => (n.tag ?? "").toUpperCase().includes(q) || n.kind.toUpperCase() === q)
      .slice(0, 12);
  }, [query, snapshot]);

  function zoomTo(node: Node) {
    const [x0, y0, x1, y1] = node.bbox;
    const target = snapshot?.pages.find((p) => p.index === node.page);
    const size = Math.max((x1 - x0) * 14, (y1 - y0) * 14, (target?.width ?? sheet.width) / 8);
    if (node.page !== page) setPage(node.page);
    setSelected(node.stable_key);
    setView({
      x: (x0 + x1) / 2 - size / 2,
      y: (y0 + y1) / 2 - (size * 0.66) / 2,
      w: size,
      h: size * 0.66,
    });
    setQuery("");
    setTouched(true);
  }

  function jumpToFinding(f: Finding, index: number) {
    // A second click on the open row always collapses it, jump or no jump.
    if (openFinding === index) {
      setOpenFinding(null);
      setFlash(null);
      return;
    }
    const matches = (snapshot?.nodes ?? []).filter((n) => n.tag && n.tag === f.subject);
    // Prefer the instance on the sheet in view: a tag can legitimately appear on several
    // sheets, and jumping to an arbitrary one points the reader at the wrong evidence.
    const match = matches.find((n) => n.page === page) ?? matches[0];
    if (match) {
      setFlash(f.subject);
      zoomTo(match);
      setOpenFinding(index);
    } else {
      setOpenFinding(index);
    }
  }

  // Wheel zoom must be a non-passive native listener: React's synthetic wheel handler cannot
  // preventDefault, and without it the page scrolls instead of the camera zooming.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      setTouched(true);
      setView((current) => {
        const v = current ?? fit;
        const rect = svg.getBoundingClientRect();
        // preserveAspectRatio letterboxes one axis; ignoring that offsets the anchor by up to
        // the letterbox width and the zoom drifts sideways at the sheet edges.
        const s = Math.min(rect.width / v.w, rect.height / v.h);
        const ox = (rect.width - v.w * s) / 2;
        const oy = (rect.height - v.h * s) / 2;
        const px = v.x + (event.clientX - rect.left - ox) / s;
        const py = v.y + (event.clientY - rect.top - oy) / s;
        const factor = event.deltaY > 0 ? 1.18 : 1 / 1.18;
        const w = Math.min(Math.max(v.w * factor, sheet.width / 60), sheet.width * 2.2);
        const h = (w / v.w) * v.h;
        return { x: px - ((px - v.x) / v.w) * w, y: py - ((py - v.y) / v.h) * h, w, h };
      });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [fit, sheet.width]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelected(null);
        setTracing(false);
        setQuery("");
        setFlash(null);
      } else if (event.key === "/" && document.activeElement?.tagName !== "INPUT") {
        event.preventDefault();
        document.getElementById("search")?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (failed) {
    return (
      <div className="empty">
        Server unreachable. <button onClick={load}>retry</button>
      </div>
    );
  }
  if (!snapshot) return <div className="empty">Loading…</div>;
  if (!snapshot.nodes.length) {
    return (
      <div className="empty">
        No graph yet — run <code>pidgraph check</code>
      </div>
    );
  }

  const findings = snapshot.findings ?? [];

  return (
    <div className="app">
      <header>
        <h1>pidgraph</h1>
        <span className="chip">
          <b>{snapshot.nodes.length}</b> nodes
        </span>
        <span className="chip">
          <b>{snapshot.edges.length}</b> edges
        </span>
        <div className="controls">
          {snapshot.pages.map((p) => (
            <button
              key={p.index}
              data-on={p.index === page}
              onClick={() => {
                setPage(p.index);
                setView(null);
                setSelected(null);
                setFlash(null);
              }}
            >
              {p.index + 1}
            </button>
          ))}
          <button
            data-on={showConfidence}
            title="colour by confidence"
            onClick={() => setShowConfidence((v) => !v)}
          >
            ●
          </button>
        </div>
        <div className="search">
          <input
            id="search"
            placeholder="find a tag  /"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && hits.length) zoomTo(hits[0]);
            }}
          />
          {hits.length > 0 && (
            <div className="results">
              {hits.map((n) => (
                <button key={n.stable_key} onClick={() => zoomTo(n)}>
                  <span className="tag">{n.tag ?? n.kind}</span>
                  <span className="k">
                    {n.kind === "unknown" ? "" : `${n.kind} · `}sheet {n.page + 1}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      <div className="main">
        <div className="stage">
          <svg
            ref={svgRef}
            className={panning ? "grabbing" : "grab"}
            viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`}
            onPointerDown={(e) => {
              (e.target as Element).setPointerCapture?.(e.pointerId);
              drag.current = { x: e.clientX, y: e.clientY, moved: false };
            }}
            onPointerMove={(e) => {
              if (!drag.current || !svgRef.current) return;
              const dx = e.clientX - drag.current.x;
              const dy = e.clientY - drag.current.y;
              if (Math.abs(dx) + Math.abs(dy) > 3) {
                drag.current.moved = true;
                setPanning(true);
              }
              if (!drag.current.moved) return;
              const rect = svgRef.current.getBoundingClientRect();
              setView((current) => {
                const v = current ?? fit;
                // Divide by the real letterboxed scale, not the element extent: with the
                // element-extent divisor the pan speed differs from the cursor on the
                // letterboxed axis and the drawing slides out from under the pointer.
                const s = Math.min(rect.width / v.w, rect.height / v.h);
                return { ...v, x: v.x - dx / s, y: v.y - dy / s };
              });
              drag.current = { x: e.clientX, y: e.clientY, moved: true };
              setTouched(true);
            }}
            onPointerUp={() => {
              if (drag.current && !drag.current.moved) {
                setSelected(null);
                setTracing(false);
                setFlash(null);
              }
              drag.current = null;
              setPanning(false);
            }}
            onPointerCancel={() => {
              drag.current = null;
              setPanning(false);
            }}
            onDoubleClick={() => setView(null)}
          >
            <rect x={box.x} y={box.y} width={box.w} height={box.h} fill="#070b0f" />
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
                  strokeWidth={on ? 2.2 : 1}
                  vectorEffect="non-scaling-stroke"
                  strokeOpacity={traced && !on ? 0.12 : 0.8}
                  strokeDasharray={e.style === "dashed" ? "4 3" : undefined}
                />
              );
            })}
            {/* Largest first, so the smallest symbol is painted last and wins the click. */}
            {[...nodes]
              .sort(
                (p, q) =>
                  (q.bbox[2] - q.bbox[0]) * (q.bbox[3] - q.bbox[1]) -
                  (p.bbox[2] - p.bbox[0]) * (p.bbox[3] - p.bbox[1]),
              )
              .map((n) => {
                const depth = traced?.get(n.stable_key);
                const dim = traced !== null && depth === undefined;
                const flashed = flash !== null && n.tag === flash;
                const colour = flashed
                  ? "#f472b6"
                  : depth === 0
                    ? "#38bdf8"
                    : showConfidence
                      ? BAND_COLOUR[confidenceBand(n.confidence)]
                      : n.kind === "instrument"
                        ? "#38bdf8"
                        : "#7c8ea0";
                const isSel = n.stable_key === selected;
                return (
                  <rect
                    key={n.stable_key}
                    className="node"
                    x={n.bbox[0]}
                    y={n.bbox[1]}
                    width={Math.max(n.bbox[2] - n.bbox[0], 2)}
                    height={Math.max(n.bbox[3] - n.bbox[1], 2)}
                    fill={isSel || flashed ? colour : "transparent"}
                    fillOpacity={isSel || flashed ? 0.28 : 0}
                    stroke={colour}
                    strokeWidth={isSel || flashed ? 2.4 : 1.1}
                    vectorEffect="non-scaling-stroke"
                    strokeOpacity={dim ? 0.1 : 0.95}
                    onPointerUp={(e) => {
                      if (drag.current?.moved) return;
                      e.stopPropagation();
                      drag.current = null;
                      setSelected(n.stable_key);
                      setFlash(null);
                      setTouched(true);
                    }}
                  >
                    <title>{n.tag ?? n.kind}</title>
                  </rect>
                );
              })}
          </svg>

          <div className="zoombar">
            <button title="zoom in" onClick={() => setView(zoomed(box, 1 / 1.4, sheet))}>
              +
            </button>
            <button title="zoom out" onClick={() => setView(zoomed(box, 1.4, sheet))}>
              −
            </button>
            <button title="fit sheet" onClick={() => setView(null)}>
              ⤢
            </button>
          </div>

          {showConfidence && (
            <div className="legend">
              {(["high", "medium", "low"] as const).map((band) => (
                <span key={band}>
                  <i className="swatch" style={{ background: BAND_COLOUR[band] }} />
                  {band}
                </span>
              ))}
            </div>
          )}

          <div className={`hint ${touched ? "gone" : ""}`}>
            scroll to zoom · drag to pan · click a symbol
          </div>

          {active && (
            <div className="card selection">
              <button className="close" onClick={() => setSelected(null)}>
                ✕
              </button>
              <p className="sel-tag tag">{active.tag ?? active.kind}</p>
              <div className="sel-chips">
                {active.kind !== "unknown" && <span className="chip">{active.kind}</span>}
                {active.dexpi_class && <span className="chip">{active.dexpi_class}</span>}
              </div>
              <div className="confbar" title={`confidence ${(active.confidence * 100).toFixed(0)}%`}>
                <i
                  style={{
                    width: `${active.confidence * 100}%`,
                    background: BAND_COLOUR[confidenceBand(active.confidence)],
                  }}
                />
              </div>
              <button data-on={tracing} onClick={() => setTracing((v) => !v)}>
                ⇢ trace{traced ? ` · ${traced.size}` : ""}
              </button>
            </div>
          )}

          {findings.length > 0 && (
            <div className="card findings">
              <h2>findings · {findings.length}</h2>
              <div className="flist">
                {findings.map((f, i) => (
                  <div key={i}>
                    <button
                      className="frow"
                      aria-label={f.title}
                      onClick={() => jumpToFinding(f, i)}
                    >
                      <span className="dot" style={{ background: SEVERITY_COLOUR[f.severity] }} />
                      <span className="t">{f.title}</span>
                    </button>
                    {openFinding === i && <div className="fdetail">{f.detail}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function zoomed(v: View, factor: number, sheet: { width: number; height: number }): View {
  const w = Math.min(Math.max(v.w * factor, sheet.width / 60), sheet.width * 2.2);
  const h = (w / v.w) * v.h;
  const cx = v.x + v.w / 2;
  const cy = v.y + v.h / 2;
  return { x: cx - w / 2, y: cy - h / 2, w, h };
}

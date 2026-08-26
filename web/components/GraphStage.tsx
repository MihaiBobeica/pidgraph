"use client";

import { useEffect, useRef, useState } from "react";
import { BAND_COLOUR, confidenceBand, type Edge, type Node } from "@/lib/graph";

type View = { x: number; y: number; w: number; h: number };

type Props = {
  nodes: Node[];
  edges: Edge[];
  sheet: { width: number; height: number };
  selected: string | null;
  tracing: boolean;
  traced: Map<string, number> | null;
  showConfidence: boolean;
  flash: string | null;
  onSelect: (key: string | null) => void;
  onTraceToggle: () => void;
};

function zoomed(v: View, factor: number, sheet: { width: number; height: number }): View {
  const w = Math.min(Math.max(v.w * factor, sheet.width / 60), sheet.width * 2.2);
  const h = (w / v.w) * v.h;
  const cx = v.x + v.w / 2;
  const cy = v.y + v.h / 2;
  return { x: cx - w / 2, y: cy - h / 2, w, h };
}

function overlayText(node: Node): string {
  const tag = (node.tag || "").trim();
  if (tag) return tag;
  const label = (node.label || "").trim();
  if (!label || /^region@/i.test(label)) return "";
  if (label.length < 2 || !/[A-Za-z]/.test(label)) return "";
  return label;
}

export default function GraphStage({
  nodes,
  edges,
  sheet,
  selected,
  tracing,
  traced,
  showConfidence,
  flash,
  onSelect,
  onTraceToggle,
}: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const [panning, setPanning] = useState(false);
  const [view, setView] = useState<View | null>(null);
  const [touched, setTouched] = useState(false);
  const fit: View = { x: 0, y: 0, w: sheet.width, h: sheet.height };
  const box = view ?? fit;
  const byKey = new Map(nodes.map((n) => [n.stable_key, n]));
  const active = selected ? (byKey.get(selected) ?? null) : null;

  useEffect(() => {
    setView(null);
  }, [sheet.width, sheet.height]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      setTouched(true);
      setView((current) => {
        const v = current ?? fit;
        const rect = svg.getBoundingClientRect();
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

  return (
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
            const s = Math.min(rect.width / v.w, rect.height / v.h);
            return { ...v, x: v.x - dx / s, y: v.y - dy / s };
          });
          drag.current = { x: e.clientX, y: e.clientY, moved: true };
          setTouched(true);
        }}
        onPointerUp={() => {
          if (drag.current && !drag.current.moved) onSelect(null);
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
            const w = Math.max(n.bbox[2] - n.bbox[0], 2);
            const h = Math.max(n.bbox[3] - n.bbox[1], 2);
            const label = overlayText(n);
            const svgH = svgRef.current?.clientHeight ?? 720;
            const unit = box.h / svgH;
            const emphasised = isSel || flashed || depth === 0;
            const fontSize = emphasised ? Math.max(h * 0.9, 11 * unit) : Math.max(h * 0.7, 8 * unit);
            const showLabel = Boolean(label) && !dim && (emphasised || Boolean(n.tag));
            return (
              <g key={n.stable_key} className="node" opacity={dim ? 0.18 : 1}>
                <rect
                  x={n.bbox[0]}
                  y={n.bbox[1]}
                  width={w}
                  height={h}
                  fill={isSel || flashed ? colour : "transparent"}
                  fillOpacity={isSel || flashed ? 0.28 : 0}
                  stroke={colour}
                  strokeWidth={isSel || flashed ? 2.4 : 1.1}
                  vectorEffect="non-scaling-stroke"
                  strokeOpacity={0.95}
                  onPointerUp={(e) => {
                    if (drag.current?.moved) return;
                    e.stopPropagation();
                    drag.current = null;
                    onSelect(n.stable_key);
                  }}
                >
                  <title>{n.tag ?? n.kind}</title>
                </rect>
                {showLabel && (
                  <text
                    className="node-label"
                    x={n.bbox[0] + w / 2}
                    y={n.bbox[1] - Math.max(fontSize * 0.2, 1.5)}
                    fontSize={fontSize}
                    textAnchor="middle"
                  >
                    {label}
                  </text>
                )}
              </g>
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
          <button className="close" onClick={() => onSelect(null)}>
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
          <button data-on={tracing} onClick={onTraceToggle}>
            ⇢ trace{traced ? ` · ${traced.size}` : ""}
          </button>
        </div>
      )}
    </div>
  );
}

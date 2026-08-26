import type { Finding, Node, Snapshot } from "./graph";

export function derivePages(nodes: Node[]): { index: number; width: number; height: number }[] {
  const indices = [...new Set(nodes.map((n) => n.page))].sort((a, b) => a - b);
  if (!indices.length) return [{ index: 0, width: 1224, height: 792 }];
  return indices.map((index) => {
    const on = nodes.filter((n) => n.page === index && Array.isArray(n.bbox));
    const w = Math.max(...on.map((n) => n.bbox[2] ?? 0), 100);
    const h = Math.max(...on.map((n) => n.bbox[3] ?? 0), 100);
    return { index, width: Math.ceil(w * 1.04), height: Math.ceil(h * 1.04) };
  });
}

export function snapshotFromNodelink(
  raw: any,
  findings: Finding[],
  source: string,
): Snapshot {
  const nodes: Node[] = (raw.nodes ?? []).map((n: any) => ({
    stable_key: String(n.id),
    kind: n.kind ?? "unknown",
    dexpi_class: n.dexpi_class ?? null,
    tag: n.tag_canonical ?? n.tag ?? null,
    label: n.label || null,
    bbox: [Number(n.x0), Number(n.y0), Number(n.x1), Number(n.y1)],
    page: Number(n.page ?? 0),
    confidence: Number(n.confidence ?? 1),
  }));
  const edges = (raw.edges ?? []).map((e: any) => ({
    source: String(e.source),
    target: String(e.target),
    style: e.style ?? null,
    evidence: e.evidence ?? "",
    confidence: Number(e.confidence ?? 1),
  }));
  return { nodes, edges, findings, pages: derivePages(nodes), source };
}

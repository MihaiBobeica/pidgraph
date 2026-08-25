// Data access. Reads come from the API layer (or a committed export when no database is
// configured), so the interface renders whether or not credentials exist -- a reader should be
// able to see the result without provisioning anything.

export type Node = {
  stable_key: string;
  kind: string;
  dexpi_class: string | null;
  tag: string | null;
  label: string | null;
  bbox: [number, number, number, number];
  page: number;
  confidence: number;
};

export type Edge = {
  source: string;
  target: string;
  style: string | null;
  evidence: string;
  confidence: number;
};

export type Finding = {
  check: string;
  status: "verified" | "finding" | "needs_review";
  severity: "info" | "low" | "medium" | "high" | "critical";
  title: string;
  detail: string;
  subject: string | null;
  confidence: number;
  graph_incomplete: boolean;
};

export type Snapshot = {
  nodes: Node[];
  edges: Edge[];
  findings: Finding[];
  pages: { index: number; width: number; height: number }[];
  source: string;
};

// Confidence is a first-class visual dimension, not a debug field. Most demonstrations show a
// clean graph and hide how much of it is a weak claim; showing it is what makes the rest
// believable.
export function confidenceBand(value: number): "high" | "medium" | "low" {
  if (value >= 0.8) return "high";
  if (value >= 0.6) return "medium";
  return "low";
}

export const BAND_COLOUR: Record<string, string> = {
  high: "#4ade80",
  medium: "#fbbf24",
  low: "#f87171",
};

export const SEVERITY_COLOUR: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#38bdf8",
  info: "#94a3b8",
};

/** Walk the graph outward from a node, following edges in both directions. */
export function trace(edges: Edge[], from: string, maxDepth = 12): Map<string, number> {
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    if (!adjacency.has(edge.source)) adjacency.set(edge.source, []);
    if (!adjacency.has(edge.target)) adjacency.set(edge.target, []);
    adjacency.get(edge.source)!.push(edge.target);
    adjacency.get(edge.target)!.push(edge.source);
  }
  const depths = new Map<string, number>([[from, 0]]);
  let frontier = [from];
  for (let depth = 1; depth <= maxDepth && frontier.length; depth++) {
    const next: string[] = [];
    for (const key of frontier) {
      for (const neighbour of adjacency.get(key) ?? []) {
        if (!depths.has(neighbour)) {
          depths.set(neighbour, depth);
          next.push(neighbour);
        }
      }
    }
    frontier = next;
  }
  return depths;
}

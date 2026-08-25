import { promises as fs } from "node:fs";
import path from "node:path";

// Sheet dimensions are derived from node extents, never hardcoded: an absolute drawing
// dimension in the interface is the same mistake the extraction pipeline forbids in itself.
function derivePages(nodes: any[]): { index: number; width: number; height: number }[] {
  const indices = [...new Set(nodes.map((n) => n.page))].sort((a, b) => a - b);
  return indices.map((index) => {
    const on = nodes.filter((n) => n.page === index && Array.isArray(n.bbox));
    const w = Math.max(...on.map((n) => n.bbox[2] ?? 0), 100);
    const h = Math.max(...on.map((n) => n.bbox[3] ?? 0), 100);
    return { index, width: Math.ceil(w * 1.04), height: Math.ceil(h * 1.04) };
  });
}

// Serves the graph. Prefers the database when configured; otherwise falls back to the committed
// export, so the interface is viewable without provisioning anything.
export const dynamic = "force-dynamic";

export async function GET() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (url && key) {
    try {
      const { createClient } = await import("@supabase/supabase-js");
      const client = createClient(url, key);
      // A single aggregated document: the REST layer caps row sets at 1000, including function
      // results, and a truncated graph would be silently wrong rather than visibly broken.
      const { data, error } = await client.rpc("graph_snapshot", {});
      if (!error && data && (data.nodes ?? []).length) {
        // The RPC returns nodes and edges only; the page list the UI iterates is derived here.
        const nodes = (data.nodes ?? []).filter((n: any) => Array.isArray(n.bbox));
        return Response.json({
          nodes,
          edges: data.edges ?? [],
          findings: [],
          pages: derivePages(nodes),
          source: "database",
        });
      }
    } catch {
      // Fall through to the committed export.
    }
  }

  // Dev runs with cwd at web/, the standalone build with cwd at the bundle root; both are tried
  // rather than assuming one layout and returning "unavailable" in the other.
  const candidates = [
    path.join(process.cwd(), "..", "outputs", "graph.json"),
    path.join(process.cwd(), "outputs", "graph.json"),
  ];
  try {
    let raw: any = null;
    for (const file of candidates) {
      try {
        raw = JSON.parse(await fs.readFile(file, "utf-8"));
        break;
      } catch {
        /* try the next location */
      }
    }
    if (!raw) throw new Error("no committed export found");
    const nodes = raw.pages.flatMap((p: any) =>
      p.graph.nodes.map((n: any) => ({
        stable_key: n.stable_key,
        kind: n.kind,
        dexpi_class: n.dexpi_class,
        // The export nests the parsed tag under attributes; a bare tag_name key never existed.
        tag: n.attributes?.tag_canonical ?? null,
        label: n.label,
        bbox: n.bbox,
        page: n.page_index,
        confidence: n.confidence,
      })),
    );
    const edges = raw.pages.flatMap((p: any) => p.graph.edges);
    return Response.json({
      nodes,
      edges,
      findings: [],
      pages: derivePages(nodes),
      source: "committed export",
    });
  } catch {
    return Response.json({ nodes: [], edges: [], findings: [], pages: [], source: "unavailable" });
  }
}

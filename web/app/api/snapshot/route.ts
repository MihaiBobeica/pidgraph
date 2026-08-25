import { promises as fs } from "node:fs";
import path from "node:path";

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
      const { data, error } = await client.rpc("graph_snapshot", { p_run: null });
      if (!error && data) return Response.json({ ...data, findings: [], source: "database" });
    } catch {
      // Fall through to the committed export.
    }
  }

  const file = path.join(process.cwd(), "..", "outputs", "graph.json");
  try {
    const raw = JSON.parse(await fs.readFile(file, "utf-8"));
    const nodes = raw.pages.flatMap((p: any) =>
      p.graph.nodes.map((n: any) => ({
        stable_key: n.stable_key,
        kind: n.kind,
        dexpi_class: n.dexpi_class,
        tag: n.tag_name ?? null,
        label: n.label,
        bbox: n.bbox,
        page: n.page_index,
        confidence: n.confidence,
      })),
    );
    const edges = raw.pages.flatMap((p: any) => p.graph.edges);
    const pages = raw.pages.map((p: any) => ({ index: p.page_index, width: 1224, height: 792 }));
    return Response.json({ nodes, edges, findings: [], pages, source: "committed export" });
  } catch {
    return Response.json({ nodes: [], edges: [], findings: [], pages: [], source: "unavailable" });
  }
}

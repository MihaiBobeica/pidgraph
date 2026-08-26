import { promises as fs } from "node:fs";
import path from "node:path";

import { snapshotFromNodelink } from "@/lib/nodelink";
import { outputsRoot } from "@/lib/files";
import type { Finding } from "@/lib/graph";

export const dynamic = "force-dynamic";

async function readFindings(dir: string): Promise<Finding[]> {
  try {
    const jsonl = await fs.readFile(path.join(dir, "findings.jsonl"), "utf-8");
    return jsonl
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } catch {
    return [];
  }
}

async function readNodelink(file: string, findings: Finding[], source: string) {
  const raw = JSON.parse(await fs.readFile(file, "utf-8"));
  return snapshotFromNodelink(raw, findings, source);
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const hash = (url.searchParams.get("hash") || "").replace(/[^a-fA-F0-9]/g, "");

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!hash && supabaseUrl && key) {
    try {
      const { createClient } = await import("@supabase/supabase-js");
      const client = createClient(supabaseUrl, key);
      const { data, error } = await client.rpc("graph_snapshot", {});
      if (!error && data && (data.nodes ?? []).length) {
        const nodes = (data.nodes ?? []).filter((n: any) => Array.isArray(n.bbox));
        const { derivePages } = await import("@/lib/nodelink");
        return Response.json({
          nodes,
          edges: data.edges ?? [],
          findings: data.findings ?? [],
          pages: derivePages(nodes),
          source: "database",
        });
      }
    } catch {
      /* fall through to files */
    }
  }

  const root = outputsRoot();
  const findings = await readFindings(root);
  const hashed = hash ? path.join(root, hash, "graph.nodelink.json") : "";
  const latest = path.join(root, "graph.nodelink.json");
  try {
    if (hashed) {
      return Response.json(await readNodelink(hashed, findings, `outputs/${hash}`));
    }
    return Response.json(await readNodelink(latest, findings, "outputs"));
  } catch {
    return Response.json({ nodes: [], edges: [], findings: [], pages: [], source: "unavailable" });
  }
}

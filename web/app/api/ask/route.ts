import { outputsRoot, runPython } from "@/lib/files";
import path from "node:path";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

export async function GET() {
  const host = (process.env.OLLAMA_HOST || "http://127.0.0.1:11434").replace(/\/$/, "");
  try {
    const response = await fetch(`${host}/api/tags`, { signal: AbortSignal.timeout(1500) });
    return Response.json({ ollama: response.ok });
  } catch {
    return Response.json({ ollama: false });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const question = String(body.question || "").trim();
    const hash = String(body.hash || "").replace(/[^a-fA-F0-9]/g, "");
    if (!question) return Response.json({ error: "missing question" }, { status: 400 });
    const graph = hash
      ? path.join(outputsRoot(), hash, "graph.nodelink.json")
      : path.join(outputsRoot(), "graph.nodelink.json");
    const result = await runPython(["-m", "pidgraph.agent", graph, question], {
      timeoutMs: 120_000,
    });
    if (result.code !== 0) {
      return Response.json({ error: result.stderr || "ask failed" }, { status: 400 });
    }
    return Response.json(JSON.parse(result.stdout.toString("utf-8") || "{}"));
  } catch (err) {
    return Response.json({ error: err instanceof Error ? err.message : "failed" }, { status: 400 });
  }
}

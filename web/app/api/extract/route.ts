import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";

import { confine, dataRoot, runPython } from "@/lib/files";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const file = confine(String(body.path || ""), dataRoot());
    if (!file.toLowerCase().endsWith(".pdf")) {
      return Response.json({ error: "only PDF files are accepted" }, { status: 400 });
    }
    const bytes = await fs.readFile(file);
    const hash = createHash("sha256").update(bytes).digest("hex");
    const result = await runPython(["-m", "pidgraph.cli", "extract", "--pid", file], {
      timeoutMs: 180_000,
    });
    if (result.code !== 0) {
      return Response.json(
        { error: result.stderr || result.stdout.toString("utf-8") || "extract failed" },
        { status: 400 },
      );
    }
    return Response.json({
      ok: true,
      hash,
      log: result.stdout.toString("utf-8"),
    });
  } catch (err) {
    return Response.json({ error: err instanceof Error ? err.message : "failed" }, { status: 400 });
  }
}

import { confine, dataRoot, runPython } from "@/lib/files";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  try {
    const file = confine(url.searchParams.get("path") || "", dataRoot());
    if (!file.toLowerCase().endsWith(".pdf")) {
      return Response.json({ error: "only PDF files are accepted" }, { status: 400 });
    }
    const page = Number(url.searchParams.get("page") || "0");
    const result = await runPython(["-m", "pidgraph.render", file, String(page)], {
      timeoutMs: 30_000,
    });
    if (result.code !== 0) {
      return Response.json({ error: result.stderr || "render failed" }, { status: 400 });
    }
    return new Response(result.stdout, { headers: { "Content-Type": "image/png" } });
  } catch (err) {
    return Response.json({ error: err instanceof Error ? err.message : "failed" }, { status: 400 });
  }
}

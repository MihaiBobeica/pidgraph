import { confine, dataRoot, runPython } from "@/lib/files";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  try {
    const file = confine(url.searchParams.get("path") || "", dataRoot());
    if (!file.toLowerCase().endsWith(".docx")) {
      return Response.json(
        { error: "HTML preview is for .docx; PDF pages are rendered as PNG" },
        { status: 400 },
      );
    }
    const result = await runPython(["-m", "pidgraph.preview", "--html", file], {
      timeoutMs: 15_000,
    });
    if (result.code !== 0) {
      return Response.json({ error: result.stderr || "preview failed" }, { status: 400 });
    }
    return new Response(result.stdout.toString("utf-8"), {
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  } catch (err) {
    return Response.json({ error: err instanceof Error ? err.message : "failed" }, { status: 400 });
  }
}

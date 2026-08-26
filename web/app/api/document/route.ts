import { confine, dataRoot, isDocumentName, runPython } from "@/lib/files";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  try {
    const file = confine(url.searchParams.get("path") || "", dataRoot());
    if (!isDocumentName(file)) {
      return Response.json({ error: "only PDF and .docx files are accepted" }, { status: 400 });
    }
    const result = await runPython(["-m", "pidgraph.preview", "--meta", file], {
      timeoutMs: 15_000,
    });
    if (result.code !== 0) {
      return Response.json({ error: result.stderr || "document info failed" }, { status: 400 });
    }
    const body = JSON.parse(result.stdout.toString("utf-8"));
    return Response.json(body);
  } catch (err) {
    return Response.json({ error: err instanceof Error ? err.message : "failed" }, { status: 400 });
  }
}

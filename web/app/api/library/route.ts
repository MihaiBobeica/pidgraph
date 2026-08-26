import { promises as fs } from "node:fs";
import path from "node:path";

import { confine, dataRoot, ensureDataRoot, isDocumentName, runPython } from "@/lib/files";

export const dynamic = "force-dynamic";

export async function GET() {
  await ensureDataRoot();
  const result = await runPython(["-m", "pidgraph.library"], { timeoutMs: 15_000 });
  if (result.code !== 0) {
    return Response.json({ error: result.stderr || "library listing failed" }, { status: 400 });
  }
  try {
    return Response.json(JSON.parse(result.stdout.toString("utf-8")));
  } catch {
    return Response.json({ error: "library listing failed" }, { status: 400 });
  }
}

export async function POST(request: Request) {
  const root = await ensureDataRoot();
  const type = request.headers.get("content-type") || "";
  try {
    if (type.includes("multipart/form-data")) {
      const form = await request.formData();
      const folder = String(form.get("folder") || "");
      const file = form.get("file");
      if (!(file instanceof File)) return Response.json({ error: "missing file" }, { status: 400 });
      const name = file.name.replace(/\\/g, "/").split("/").pop() || "upload.pdf";
      if (!isDocumentName(name)) {
        return Response.json({ error: "only PDF and .docx files are accepted" }, { status: 400 });
      }
      const destDir = confine(folder, root);
      try {
        const stat = await fs.stat(destDir);
        if (!stat.isDirectory()) {
          return Response.json({ error: "folder does not exist" }, { status: 400 });
        }
      } catch {
        return Response.json({ error: "folder does not exist" }, { status: 400 });
      }
      const dest = confine(`${folder}/${name}`.replace(/^\//, ""), root);
      if (!isDocumentName(dest)) {
        return Response.json({ error: "only PDF and .docx files are accepted" }, { status: 400 });
      }
      const bytes = Buffer.from(await file.arrayBuffer());
      await fs.writeFile(dest, bytes);
      return Response.json({ ok: true, path: path.relative(root, dest).replace(/\\/g, "/") });
    }
    return Response.json({ error: "unknown action" }, { status: 400 });
  } catch (err) {
    return Response.json({ error: err instanceof Error ? err.message : "failed" }, { status: 400 });
  }
}

export async function DELETE(request: Request) {
  const root = dataRoot();
  try {
    const body = await request.json();
    const target = confine(String(body.path || ""), root);
    const stat = await fs.stat(target);
    if (stat.isDirectory()) {
      return Response.json({ error: "folders cannot be deleted" }, { status: 400 });
    }
    await fs.unlink(target);
    return Response.json({ ok: true });
  } catch (err) {
    return Response.json({ error: err instanceof Error ? err.message : "failed" }, { status: 400 });
  }
}

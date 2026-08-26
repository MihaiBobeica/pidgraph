import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { promises as fs } from "node:fs";
import path from "node:path";

export function repoRoot(): string {
  const cwd = process.cwd();
  const parent = path.join(cwd, "..");
  if (existsSync(path.join(cwd, "pidgraph"))) return cwd;
  return parent;
}

export function dataRoot(): string {
  if (process.env.PIDGRAPH_INPUT_DIR) return path.resolve(process.env.PIDGRAPH_INPUT_DIR);
  return path.join(repoRoot(), "data");
}

export function outputsRoot(): string {
  return path.join(repoRoot(), "outputs");
}

export function pythonBin(): string {
  const root = repoRoot();
  const win = path.join(root, ".venv", "Scripts", "python.exe");
  const nix = path.join(root, ".venv", "bin", "python");
  if (existsSync(win)) return win;
  if (existsSync(nix)) return nix;
  return "python";
}

export const DOCUMENT_SUFFIXES = [".pdf", ".docx"] as const;

export function isDocumentName(name: string): boolean {
  const lower = name.toLowerCase();
  return DOCUMENT_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}

export function confine(relative: string, root = dataRoot()): string {
  const base = path.resolve(root);
  const text = (relative || "").replace(/\\/g, "/").replace(/^\/+/, "");
  if (!text) return base;
  const parts = text.split("/").filter(Boolean);
  if (parts.includes("..")) {
    throw new Error("path escapes the data directory");
  }
  const candidate = path.resolve(base, ...parts);
  const rel = path.relative(base, candidate);
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    throw new Error("path escapes the data directory");
  }
  return candidate;
}

export async function runPython(args: string[], opts?: { timeoutMs?: number }): Promise<{
  code: number;
  stdout: Buffer;
  stderr: string;
}> {
  const timeoutMs = opts?.timeoutMs ?? 120_000;
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBin(), args, { cwd: repoRoot() });
    const chunks: Buffer[] = [];
    const err: Buffer[] = [];
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error("python timed out"));
    }, timeoutMs);
    child.stdout.on("data", (d) => chunks.push(d));
    child.stderr.on("data", (d) => err.push(d));
    child.on("error", reject);
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({
        code: code ?? 1,
        stdout: Buffer.concat(chunks),
        stderr: Buffer.concat(err).toString("utf-8"),
      });
    });
  });
}

export async function ensureDataRoot(): Promise<string> {
  const root = dataRoot();
  await fs.mkdir(root, { recursive: true });
  return root;
}

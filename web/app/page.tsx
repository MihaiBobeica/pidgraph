"use client";

import { useEffect, useMemo, useState } from "react";
import Chat from "@/components/Chat";
import GraphStage from "@/components/GraphStage";
import Library, { type LibEntry } from "@/components/Library";
import PdfPage from "@/components/PdfPage";
import { trace, type Node, type Snapshot } from "@/lib/graph";

function posix(path: string): string {
  return path.replace(/\\/g, "/");
}

function isSopPath(path: string | null): boolean {
  if (!path) return false;
  const p = posix(path).toLowerCase();
  if (p.endsWith(".docx")) return true;
  return p.split("/")[0] === "sop";
}

function isDrawingPdf(path: string | null): boolean {
  if (!path) return false;
  return posix(path).toLowerCase().endsWith(".pdf") && !isSopPath(path);
}

type DocMeta = { kind: string; pages: number };

export default function Page() {
  const [tree, setTree] = useState<LibEntry[]>([]);
  const [pdfPath, setPdfPath] = useState<string | null>(null);
  const [hash, setHash] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [mode, setMode] = useState<"graph" | "pdf">("graph");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [tracing, setTracing] = useState(false);
  const [showConfidence, setShowConfidence] = useState(true);
  const [query, setQuery] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [ollama, setOllama] = useState<boolean | null>(null);
  const [docMeta, setDocMeta] = useState<DocMeta | null>(null);

  const refreshTree = () => {
    fetch("/api/library")
      .then((r) => r.json())
      .then((d) => setTree(d.tree ?? []));
  };

  const loadSnapshot = (nextHash: string | null) => {
    const q = nextHash ? `?hash=${nextHash}` : "";
    fetch(`/api/snapshot${q}`)
      .then((r) => r.json())
      .then((data: Snapshot) => {
        setSnapshot(data);
        if (data.pages?.length) setPage(data.pages[0].index);
      });
  };

  useEffect(() => {
    refreshTree();
    loadSnapshot(null);
    fetch("/api/ask")
      .then((r) => r.json())
      .then((d) => setOllama(Boolean(d.ollama)))
      .catch(() => setOllama(false));
  }, []);

  async function selectFile(path: string) {
    setPdfPath(path);
    setSelected(null);
    setFlash(null);
    setPage(0);
    if (!isDrawingPdf(path)) {
      setMode("pdf");
      setBusy(null);
      try {
        const r = await fetch(`/api/document?path=${encodeURIComponent(path)}`);
        const data = await r.json();
        setDocMeta({ kind: data.kind ?? "docx", pages: Number(data.pages) || 1 });
      } catch {
        setDocMeta({ kind: path.toLowerCase().endsWith(".docx") ? "docx" : "pdf", pages: 1 });
      }
      return;
    }
    setDocMeta(null);
    setBusy("extracting…");
    try {
      const r = await fetch("/api/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      const data = await r.json();
      if (data.hash) {
        setHash(data.hash);
        loadSnapshot(data.hash);
      } else {
        loadSnapshot(null);
      }
    } catch {
      loadSnapshot(null);
    } finally {
      setBusy(null);
    }
  }

  const sheet = snapshot?.pages.find((p) => p.index === page) ?? {
    index: 0,
    width: 1224,
    height: 792,
  };
  const nodes = useMemo(
    () =>
      (snapshot?.nodes ?? []).filter(
        (n) =>
          n.page === page &&
          Array.isArray(n.bbox) &&
          n.bbox.length === 4 &&
          n.bbox.every((v) => Number.isFinite(v)),
      ),
    [snapshot, page],
  );
  const keys = useMemo(() => new Set(nodes.map((n) => n.stable_key)), [nodes]);
  const edges = useMemo(
    () => (snapshot?.edges ?? []).filter((e) => keys.has(e.source) && keys.has(e.target)),
    [snapshot, keys],
  );
  const traced = useMemo(
    () => (tracing && selected ? trace(edges, selected) : null),
    [tracing, selected, edges],
  );
  const hits = useMemo(() => {
    const q = query.trim().toUpperCase();
    if (!q || !snapshot) return [];
    return snapshot.nodes
      .filter((n) => (n.tag ?? "").toUpperCase().includes(q) || n.kind.toUpperCase() === q)
      .slice(0, 12);
  }, [query, snapshot]);

  const pageIndexes =
    pdfPath && !isDrawingPdf(pdfPath)
      ? Array.from({ length: docMeta?.pages ?? 1 }, (_, i) => i)
      : (snapshot?.pages ?? []).map((p) => p.index);

  function jumpTo(node: Node) {
    setPage(node.page);
    setSelected(node.stable_key);
    setFlash(node.tag);
    setQuery("");
    setMode("graph");
  }

  function jumpTag(tag: string) {
    const match =
      snapshot?.nodes.find((n) => n.tag === tag && n.page === page) ??
      snapshot?.nodes.find((n) => n.tag === tag);
    if (match) jumpTo(match);
    else setFlash(tag);
  }

  return (
    <div className="app">
      <header>
        <h1>pidgraph</h1>
        <span className="chip">
          <b>{snapshot?.nodes.length ?? 0}</b> nodes
        </span>
        <span className="chip">
          <b>{snapshot?.edges.length ?? 0}</b> edges
        </span>
        <div className="controls">
          <button data-on={mode === "graph"} onClick={() => setMode("graph")}>
            Graph
          </button>
          <button data-on={mode === "pdf"} onClick={() => setMode("pdf")}>
            Doc
          </button>
          {pageIndexes.map((index) => (
            <button
              key={index}
              data-on={index === page}
              onClick={() => {
                setPage(index);
                setSelected(null);
                setFlash(null);
              }}
            >
              {index + 1}
            </button>
          ))}
          <button data-on={showConfidence} title="colour by confidence" onClick={() => setShowConfidence((v) => !v)}>
            ●
          </button>
        </div>
        <div className="search">
          <input
            id="search"
            placeholder="find a tag  /"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && hits.length) jumpTo(hits[0]);
            }}
          />
          {hits.length > 0 && (
            <div className="results">
              {hits.map((n) => (
                <button key={n.stable_key} onClick={() => jumpTo(n)}>
                  <span className="tag">{n.tag ?? n.kind}</span>
                  <span className="k">
                    {n.kind === "unknown" ? "" : `${n.kind} · `}sheet {n.page + 1}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      <div className="workspace">
        <Library
          tree={tree}
          selected={pdfPath}
          busy={busy}
          onSelect={selectFile}
          onRefresh={refreshTree}
        />
        <div className="middle">
          {mode === "pdf" ? (
            <PdfPage pdfPath={pdfPath} page={page} />
          ) : (
            <GraphStage
              nodes={nodes}
              edges={edges}
              sheet={sheet}
              selected={selected}
              tracing={tracing}
              traced={traced}
              showConfidence={showConfidence}
              flash={flash}
              onSelect={(key) => {
                setSelected(key);
                setTracing(false);
                setFlash(null);
              }}
              onTraceToggle={() => setTracing((v) => !v)}
            />
          )}
        </div>
        <aside className="pane right">
          <Chat findings={snapshot?.findings ?? []} ollama={ollama} hash={hash} onJump={jumpTag} />
        </aside>
      </div>
    </div>
  );
}

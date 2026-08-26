"use client";

import { useState, type FormEvent } from "react";
import { SEVERITY_COLOUR, type Finding } from "@/lib/graph";

type Props = {
  findings: Finding[];
  ollama: boolean | null;
  hash: string | null;
  onJump: (tag: string) => void;
};

export default function Chat({ findings, ollama, hash, onJump }: Props) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const issues = findings.filter((f) => f.status !== "verified");

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    try {
      const r = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, hash }),
      });
      const data = await r.json();
      setAnswer(data.answer || data.error || "no answer");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      <h2>SOP mismatches</h2>
      <div className="flist">
        {issues.length === 0 && <p className="muted">No discrepancies in the last check.</p>}
        {issues.map((f, i) => (
          <button
            key={i}
            className="frow"
            onClick={() => f.subject && onJump(f.subject)}
          >
            <span className="dot" style={{ background: SEVERITY_COLOUR[f.severity] }} />
            <span className="t">{f.title}</span>
          </button>
        ))}
      </div>
      <h2>Ask the graph</h2>
      <p className="muted">
        {ollama === false
          ? "Ollama is not running. Answers fall back to graph tools."
          : "Local Llama phrases what the graph tools find. Performance is not a goal."}
      </p>
      <form onSubmit={ask} className="ask">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
            placeholder="Where does MV-715-02A connect?"
        />
        <button disabled={busy}>{busy ? "…" : "ask"}</button>
      </form>
      {answer && <pre className="answer">{answer}</pre>}
    </div>
  );
}

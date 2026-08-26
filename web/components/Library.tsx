"use client";

export type LibEntry = {
  name: string;
  path: string;
  type: "folder" | "pdf" | "docx";
  children?: LibEntry[];
};

type Props = {
  tree: LibEntry[];
  selected: string | null;
  busy: string | null;
  onSelect: (path: string) => void;
  onRefresh: () => void;
};

const ACCEPT =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function FilePicker({
  folder,
  onPick,
}: {
  folder: string;
  onPick: (folder: string, file: File) => void;
}) {
  return (
    <label className="lib-add" title="Add file" aria-label="Add file">
      +
      <input
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onPick(folder, file);
          e.target.value = "";
        }}
      />
    </label>
  );
}

export default function Library({ tree, selected, busy, onSelect, onRefresh }: Props) {
  async function upload(folder: string, file: File) {
    const form = new FormData();
    form.set("folder", folder);
    form.set("file", file);
    await fetch("/api/library", { method: "POST", body: form });
    onRefresh();
  }

  async function remove(path: string) {
    if (!window.confirm(`Remove ${path}?`)) return;
    await fetch("/api/library", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    onRefresh();
  }

  function render(entries: LibEntry[], depth = 0) {
    return entries.map((entry) => (
      <div key={entry.path} className="lib-branch" data-depth={depth}>
        {entry.type === "folder" ? (
          <div className="lib-row">
            <span className="lib-name">{entry.name}</span>
            <FilePicker folder={entry.path} onPick={upload} />
          </div>
        ) : (
          <div className="lib-row">
            <button
              className="lib-file"
              data-on={selected === entry.path}
              onClick={() => onSelect(entry.path)}
            >
              {entry.name}
            </button>
            <button className="lib-act lib-act-remove" onClick={() => remove(entry.path)}>
              Remove
            </button>
          </div>
        )}
        {entry.children ? render(entry.children, depth + 1) : null}
      </div>
    ));
  }

  return (
    <aside className="pane library">
      <h2>data</h2>
      <div className="lib-tree">{tree.length ? render(tree) : <p className="muted">No files yet.</p>}</div>
      {busy && <p className="muted">{busy}</p>}
    </aside>
  );
}

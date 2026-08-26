"use client";

type Props = { pdfPath: string | null; page: number };

export default function PdfPage({ pdfPath, page }: Props) {
  if (!pdfPath) return <div className="empty">Select a file.</div>;
  if (pdfPath.toLowerCase().endsWith(".docx")) {
    return (
      <iframe
        className="docx-stage"
        title={pdfPath}
        src={`/api/preview?path=${encodeURIComponent(pdfPath)}`}
      />
    );
  }
  const src = `/api/render?path=${encodeURIComponent(pdfPath)}&page=${page}`;
  return (
    <div className="pdf-stage">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={`page ${page + 1}`} />
    </div>
  );
}

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "pidgraph",
  description: "P&ID drawings as a standards-conformant plant graph",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

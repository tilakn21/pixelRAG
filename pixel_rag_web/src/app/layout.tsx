// pixel_rag_web/src/app/layout.tsx
import type { Metadata, Viewport } from "next";
import "./globals.css";
import TopNav from "@/components/TopNav";

export const metadata: Metadata = {
  title: "PixelRAG",
  description: "A quiet local archive for searching, curating, and understanding your photography.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="light">
      <body>
        <TopNav />
        <main className="main-stage">
          <div className="shell-container">{children}</div>
        </main>
      </body>
    </html>
  );
}

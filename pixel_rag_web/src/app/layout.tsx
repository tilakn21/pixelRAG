// pixel_rag_web/src/app/layout.tsx
import type { Metadata, Viewport } from "next";
import "./globals.css";
import TopNav from "@/components/TopNav";

import { Inter, Outfit } from "next/font/google";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-outfit",
  display: "swap",
});

export const metadata: Metadata = {
  title: "PixelRAG",
  description: "Local-first AI photo intelligence",
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
    <html lang="en" data-theme="light" className={`${inter.variable} ${outfit.variable}`}>
      <body>
        <TopNav />
        <main className="main-content">
          <div className="container">{children}</div>
        </main>
      </body>
    </html>
  );
}

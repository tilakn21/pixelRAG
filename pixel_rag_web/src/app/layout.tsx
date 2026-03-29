// pixel_rag_web/src/app/layout.tsx
import type { Metadata, Viewport } from "next";
import "./globals.css";
import TopNav from "@/components/TopNav";
import Footer from "@/components/Footer";

import { Space_Grotesk, VT323 } from "next/font/google";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-grotesk",
  display: "swap",
});

const vt323 = VT323({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-pixel",
  display: "swap",
});

export const metadata: Metadata = {
  title: "PixelRAG Index",
  description: "A brutalist curation interface for structural photography.",
};

export const head = (
  <>
    <link rel="preload" href="/animations gifs/logo.mp4" as="video" type="video/mp4" />
    <link rel="preload" href="/animations gifs/loading_fullscreen_animation.mp4" as="video" type="video/mp4" />
  </>
);

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
    <html lang="en" className={`${spaceGrotesk.variable} ${vt323.variable}`}>
      <body>
        {/* Persistent Hidden Cache for Core Assets */}
        <div style={{ position: "absolute", width: 0, height: 0, overflow: "hidden", opacity: 0, pointerEvents: "none" }}>
          <video preload="auto" muted><source src="/animations gifs/logo.mp4" type="video/mp4" /></video>
          <video preload="auto" muted><source src="/animations gifs/loading_fullscreen_animation.mp4" type="video/mp4" /></video>
        </div>
        <TopNav />
        <main className="main-stage">
          <div className="shell-container content-wrap">{children}</div>
        </main>
        <Footer />
      </body>
    </html>
  );
}

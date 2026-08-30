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

// NOTE: `export const head` was removed — it is not an App Router API and was
// silently doing nothing. The hidden <video preload="auto"> block below it was
// doing something, though: eagerly downloading logo.mp4 (3.8 MB) and
// loading_fullscreen_animation.mp4 (2.7 MB) on EVERY page load, 6.5 MB before
// any photo rendered. The logo now loads naturally with the nav that shows it,
// and the loading animation loads only when FullscreenLoader mounts.

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
        <TopNav />
        <main className="main-stage">
          <div className="shell-container content-wrap">{children}</div>
        </main>
        <Footer />
      </body>
    </html>
  );
}

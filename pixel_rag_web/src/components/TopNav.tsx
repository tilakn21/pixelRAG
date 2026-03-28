// pixel_rag_web/src/components/TopNav.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import LibrarySelector from "./LibrarySelector";

export default function TopNav() {
  const pathname = usePathname();

  const links = [
    { href: "/gallery", label: "Gallery" },
    { href: "/search", label: "Search" },
    { href: "/people", label: "People" },
  ];

  return (
    <>
      <nav className="top-nav">
        <div style={{ display: "flex", alignItems: "center" }}>
          <Link href="/" className="top-nav__logo">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>
              <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
              <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
            </svg>
            PixelRAG
          </Link>
          <LibrarySelector />
        </div>
        <div className="top-nav__links">
          {links.map((link) => {
            const isActive = link.href === "/gallery" && pathname === "/" ? false : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`top-nav__item ${isActive ? "top-nav__item--active" : ""}`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </nav>
      {/* Absolute positioning to stick under the nav */}
      <div style={{ position: "fixed", top: "var(--nav-height)", zIndex: 1000, width: "100%" }}>
        <div className="vintage-rainbow-bar"></div>
      </div>
    </>
  );
}

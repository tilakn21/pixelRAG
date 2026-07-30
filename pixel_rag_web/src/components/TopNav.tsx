// pixel_rag_web/src/components/TopNav.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import LibrarySelector from "./LibrarySelector";

export default function TopNav() {
  const pathname = usePathname();

  const links = [
    { href: "/", label: "Index", icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg> },
    { href: "/photos", label: "Archive", icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><path d="M21 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v3"/><path d="m3 8 9 6 9-6"/><rect width="18" height="12" x="3" y="13" rx="2"/></svg> },
    { href: "/gallery", label: "Gallery", icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg> },
    { href: "/search", label: "Search", icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg> },
    { href: "/people", label: "People", icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg> },
    { href: "/graph", label: "Graph", icon: <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/></svg> },
  ];

  return (
    <nav className="top-nav">
      <div className="shell-container top-nav__bar">
        <div className="top-nav__lead">
          <Link href="/" className="top-nav__brand">
            <span className="top-nav__mark" aria-hidden="true" style={{ border: "var(--border-thick)", borderRadius: "12px", background: "var(--sun-yellow)", overflow: "hidden", position: "relative" }}>
              <video
                autoPlay
                loop
                muted
                playsInline
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              >
                <source src="/animations gifs/logo.mp4" type="video/mp4" />
              </video>
            </span>
            <span style={{ display: "flex", flexDirection: "column" }}>
              <strong style={{ fontFamily: "var(--font-pixel)", fontSize: "1.4rem", textTransform: "uppercase", lineHeight: 1 }}>PixelRAG</strong>
              <span className="top-nav__caption" style={{ fontFamily: "var(--font-pixel)", fontSize: "0.6rem", color: "var(--obsidian)", opacity: 0.5 }}>[ SYSTEM_ONLINE ]</span>
            </span>
          </Link>
          <LibrarySelector />
        </div>

        <div className="top-nav__links" role="navigation" aria-label="Primary">
          {links.map((link) => {
            const isActive =
              link.href === "/"
                ? pathname === "/"
                : pathname.startsWith(link.href);

            return (
              <Link
                key={link.href}
                href={link.href}
                className={`top-nav__link ${isActive ? "top-nav__link--active" : ""}`}
                style={{ 
                  fontFamily: "var(--font-pixel)", 
                  textTransform: "uppercase", 
                  fontSize: "0.85rem", 
                  padding: "8px 16px",
                  border: isActive ? "var(--border-thick)" : "2px solid rgba(0,0,0,0.05)",
                  background: isActive ? "var(--electric-blue)" : "var(--gallery-white)",
                  color: isActive ? "#fff" : "var(--obsidian)",
                  borderRadius: "12px",
                  transition: "all 0.1s",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  boxShadow: isActive ? "var(--shadow-tiny)" : "none"
                }}
              >
                {link.icon}
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}

// pixel_rag_web/src/components/TopNav.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import LibrarySelector from "./LibrarySelector";

export default function TopNav() {
  const pathname = usePathname();

  const links = [
    { href: "/", label: "Index" },
    { href: "/photos", label: "Archive" },
    { href: "/gallery", label: "Gallery" },
    { href: "/search", label: "Search" },
    { href: "/people", label: "People" },
  ];

  return (
    <nav className="top-nav">
      <div className="shell-container top-nav__bar">
        <div className="top-nav__lead">
          <Link href="/" className="top-nav__brand">
            <span className="top-nav__mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2.5" y="2.5" width="19" height="19" rx="5" />
                <circle cx="12" cy="12" r="4.25" />
                <path d="M18 6.25h.01" />
              </svg>
            </span>
            <span>
              <strong>PixelRAG</strong>
              <span className="top-nav__caption">Data as elegance</span>
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
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}

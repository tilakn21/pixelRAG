"use client";

export default function Footer() {
  const currentYear = new Date().getFullYear();
  
  return (
    <footer className="footer" style={{ marginTop: "auto", borderTop: "var(--border-thick)", background: "var(--obsidian)" }}>
      {/* Immersive Cinematic Footer */}
      <section className="video-panel" style={{ minHeight: "480px", position: "relative", overflow: "hidden" }}>
        <video 
          autoPlay 
          loop 
          muted 
          playsInline 
          style={{ opacity: 0.5, filter: "grayscale(20%)" }}
        >
          <source src="/animations gifs/From KlickPin CF Zeynep on Instagram Adobe After Effects experiments 🖥️ motiongraphics happymotion animation motiondesign kinetictypography kinetictype [Video] [Video] _ Motion graphics inspiration Motion design Motion design animation.mp4" type="video/mp4" />
        </video>
        
        <div className="video-overlay" style={{ padding: "80px 20px", textAlign: "center", alignItems: "center", justifyContent: "center", display: "flex", flexDirection: "column" }}>
          <div style={{ marginBottom: "40px" }}>
            <span className="eyebrow" style={{ color: "var(--sun-yellow)", fontFamily: "var(--font-pixel)", fontSize: "0.8rem", letterSpacing: "0.2em" }}>
              [ SYSTEM_FINAL_SEQUENCE ]
            </span>
            <h2 style={{ fontFamily: "var(--font-pixel)", fontSize: "clamp(2.5rem, 8vw, 6rem)", textTransform: "uppercase", margin: "12px 0", textShadow: "6px 6px 0 rgba(0,0,0,0.8)", lineHeight: "0.9" }}>
              PIXELRAG<br />// ARCHIVE
            </h2>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "1rem", maxWidth: "650px", marginTop: "24px", opacity: 0.8, color: "#fff", lineHeight: "1.6" }}>
              Resolving your archive through recursive neural clusters and high-fidelity spatial analysis. 
              The architectural memory engine is now stable.
            </p>
          </div>

          <div style={{ marginTop: "auto", borderTop: "1px solid rgba(255,255,255,0.2)", paddingTop: "32px", width: "min(650px, 100%)", display: "flex", flexDirection: "column", gap: "10px" }}>
            <span style={{ fontFamily: "var(--font-pixel)", fontSize: "0.85rem", color: "var(--sun-yellow)" }}>
              © {currentYear} PIXEL_RAG_SYSTEM // V1.0.4
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.65rem", opacity: 0.5, color: "#fff", textTransform: "uppercase", letterSpacing: "0.1em" }}>
              NODAL_AUTHORITY_7729 // REGION: LOCALHOST // ARCHIVE_STATUS: INDEXED
            </span>
          </div>
        </div>
      </section>
    </footer>
  );
}

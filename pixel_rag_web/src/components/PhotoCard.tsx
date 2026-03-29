// pixel_rag_web/src/components/PhotoCard.tsx
"use client";

import { getThumbUrl } from "@/lib/api";
import { formatDate, formatSceneCategory } from "@/lib/display";
import type { Photo } from "@/lib/types";

interface PhotoCardProps {
  photo: Photo;
  onClick: () => void;
  libHash?: string;
}

export default function PhotoCard({ photo, onClick, libHash }: PhotoCardProps) {
  return (
    <button 
      className="photo-card" 
      onClick={onClick} 
      type="button"
      style={{
        border: "var(--border-thick)",
        borderRadius: "16px",
        overflow: "hidden",
        position: "relative",
        background: "#000",
        transition: "all 0.15s var(--ease-soft)",
        boxShadow: "none",
        display: "inline-block",
        width: "100%",
        marginBottom: "20px"
      }}
    >
      <style jsx>{`
        .photo-card:hover {
          transform: translate(-4px, -4px);
          box-shadow: 6px 6px 0px var(--obsidian);
        }
      `}</style>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className="photo-card__image"
        src={getThumbUrl(photo.id, 800, libHash)}
        alt={photo.filename}
        loading="lazy"
        style={{ width: "100%", display: "block", transition: "opacity 0.2s" }}
      />
      
      <div className="photo-card__topline" style={{ position: "absolute", top: "12px", left: "12px", right: "12px", display: "flex", justifyContent: "space-between", pointerEvents: "none" }}>
        <span style={{ background: "var(--electric-blue)", color: "#fff", fontFamily: "var(--font-pixel)", fontSize: "0.7rem", padding: "4px 8px", borderRadius: "4px", textTransform: "uppercase", border: "1px solid #000" }}>
          {formatSceneCategory(photo.scene_category)}
        </span>
        {photo.has_faces ? (
          <span style={{ background: "var(--sun-yellow)", color: "#000", fontFamily: "var(--font-pixel)", fontSize: "0.7rem", padding: "4px 8px", borderRadius: "4px", textTransform: "uppercase", border: "1px solid #000" }}>
            IDENTITY_RESOLVED
          </span>
        ) : null}
      </div>

      <div className="photo-card__footer" style={{ position: "absolute", bottom: "0", left: "0", right: "0", background: "rgba(0,0,0,0.8)", backdropFilter: "blur(4px)", color: "#fff", padding: "8px 12px", display: "flex", justifyContent: "space-between", fontSize: "0.7rem", fontFamily: "var(--font-pixel)", borderTop: "1px solid rgba(255,255,255,0.1)", textTransform: "uppercase" }}>
        <span>{formatDate(photo.taken_at)}</span>
        <span style={{ color: "var(--neon-green)" }}>{photo.person_names.length > 0 ? `[${photo.person_names.length}]_FACES` : "EMPTY_FRAME"}</span>
      </div>
    </button>
  );
}

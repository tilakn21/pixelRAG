// pixel_rag_web/src/components/PhotoCard.tsx
"use client";

import { getThumbUrl } from "@/lib/api";
import { formatDate, formatSceneCategory } from "@/lib/display";
import type { Photo } from "@/lib/types";

interface PhotoCardProps {
  photo: Photo;
  onClick: () => void;
  libHash?: string;
  matchedFaceId?: number | null;
  selectable?: boolean;
  selected?: boolean;
}

export default function PhotoCard({
  photo,
  onClick,
  libHash,
  matchedFaceId,
  selectable,
  selected,
}: PhotoCardProps) {
  return (
    <button
      className="photo-card"
      onClick={onClick}
      type="button"
      aria-pressed={selectable ? !!selected : undefined}
      style={{
        border: selected ? "4px solid var(--electric-purple)" : "var(--border-thick)",
        borderRadius: "16px",
        overflow: "hidden",
        position: "relative",
        background: "#000",
        transition: "all 0.15s var(--ease-soft)",
        boxShadow: "none",
        display: "inline-block",
        width: "100%",
        marginBottom: "20px",
        opacity: selectable && !selected ? 0.72 : 1,
      }}
    >
      {selectable && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            top: 12,
            left: 12,
            zIndex: 12,
            width: 28,
            height: 28,
            borderRadius: 8,
            border: "2px solid #000",
            background: selected ? "var(--electric-purple)" : "rgba(255,255,255,.92)",
            display: "grid",
            placeItems: "center",
            color: "#fff",
            fontFamily: "var(--font-pixel)",
            fontSize: 15,
            boxShadow: "2px 2px 0 rgba(0,0,0,.4)",
          }}
        >
          {selected ? "✓" : ""}
        </span>
      )}
      <style jsx>{`
        .photo-card:hover {
          transform: translate(-4px, -4px);
          box-shadow: 6px 6px 0px var(--obsidian);
        }
        .face-inset {
           position: absolute;
           bottom: 12px;
           right: 12px;
           width: 64px;
           height: 64px;
           border: 3px solid var(--sun-yellow);
           border-radius: 8px;
           background: #000;
           box-shadow: 4px 4px 0px rgba(0,0,0,0.5);
           overflow: hidden;
           z-index: 10;
        }
      `}</style>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className="photo-card__image"
        src={photo.thumbnail_url ? `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${photo.thumbnail_url}` : getThumbUrl(photo.id, 800, libHash)}
        alt={photo.filename}
        loading="lazy"
        style={{ width: "100%", display: "block", transition: "opacity 0.2s" }}
      />

      {/* Identity Inset Alignment */}
      {matchedFaceId && (
        <div className="face-inset">
           {/* eslint-disable-next-line @next/next/no-img-element */}
           <img 
              src={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/media/face/${matchedFaceId}?h=${libHash || photo.lib_hash || ""}`}
              alt="Identity match"
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
           />
        </div>
      )}
      
      <div className="photo-card__topline" style={{ position: "absolute", top: "12px", left: "12px", right: "12px", display: "flex", justifyContent: "space-between", pointerEvents: "none" }}>
        <div style={{ display: "flex", gap: "8px" }}>
          <span style={{ background: "var(--electric-blue)", color: "#fff", fontFamily: "var(--font-pixel)", fontSize: "0.7rem", padding: "4px 8px", borderRadius: "4px", textTransform: "uppercase", border: "1px solid #000" }}>
            {formatSceneCategory(photo.scene_category)}
          </span>
          {photo.semantic_score != null && (
            <span style={{ background: "var(--neon-green)", color: "#000", fontFamily: "var(--font-pixel)", fontSize: "0.7rem", padding: "4px 8px", borderRadius: "4px", border: "1px solid #000", fontWeight: "bold" }}>
              {(photo.semantic_score * 100).toFixed(1)}% MATCH
            </span>
          )}
        </div>
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

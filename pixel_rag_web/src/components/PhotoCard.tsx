// pixel_rag_web/src/components/PhotoCard.tsx
"use client";

import { getThumbUrl } from "@/lib/api";
import type { Photo } from "@/lib/types";

const CATEGORY_COLORS: Record<string, string> = {
  people: "var(--cat-people)",
  landscape: "var(--cat-landscape)",
  food: "var(--cat-food)",
  architecture: "var(--cat-architecture)",
  document: "var(--cat-document)",
  other: "var(--cat-other)",
};

interface PhotoCardProps {
  photo: Photo;
  onClick: () => void;
  libHash?: string;
}

export default function PhotoCard({ photo, onClick, libHash }: PhotoCardProps) {
  const dotColor =
    CATEGORY_COLORS[photo.scene_category ?? "other"] ?? "var(--cat-other)";

  return (
    <div className="photo-card" onClick={onClick}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={getThumbUrl(photo.id, 400, libHash)}
        alt={photo.filename}
        loading="lazy"
      />
      <span
        className="photo-card__category-dot"
        style={{ backgroundColor: dotColor }}
      />
      {photo.has_faces && (
        <svg
          className="photo-card__face-icon"
          viewBox="0 0 24 24"
          fill="currentColor"
        >
          <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
        </svg>
      )}
      <div className="photo-card__overlay">
        <span style={{ fontSize: "var(--text-xs)", color: "rgba(255,255,255,0.8)" }}>
          {photo.scene_category ?? ""}
        </span>
        {photo.taken_at && (
          <span style={{ fontSize: "var(--text-xs)", color: "rgba(255,255,255,0.6)" }}>
            {new Date(photo.taken_at).toLocaleDateString()}
          </span>
        )}
      </div>
    </div>
  );
}

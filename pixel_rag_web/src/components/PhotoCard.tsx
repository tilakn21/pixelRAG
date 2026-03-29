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
    <button className="photo-card" onClick={onClick} type="button">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className="photo-card__image"
        src={getThumbUrl(photo.id, 800, libHash)}
        alt={photo.filename}
        loading="lazy"
      />
      <div className="photo-card__overlay" aria-hidden="true" />

      <div className="photo-card__topline">
        <span className="photo-card__badge">{formatSceneCategory(photo.scene_category)}</span>
        {photo.has_faces ? <span className="photo-card__signal">Faces</span> : null}
      </div>

      <div className="photo-card__footer">
        <span>{formatDate(photo.taken_at)}</span>
        <span>{photo.person_names.length > 0 ? `${photo.person_names.length} identities` : "Quiet frame"}</span>
      </div>
    </button>
  );
}

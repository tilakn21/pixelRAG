// pixel_rag_web/src/components/PhotoGrid.tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchPhotos, getPhotoUrl } from "@/lib/api";
import type { Photo } from "@/lib/types";
import PhotoCard from "./PhotoCard";

interface PhotoGridProps {
  /** If provided, uses these photos directly instead of fetching */
  photos?: Photo[];
  /** Category filter for paginated mode */
  category?: string | null;
}

export default function PhotoGrid({ photos: staticPhotos, category }: PhotoGridProps) {
  const [photos, setPhotos] = useState<Photo[]>(staticPhotos ?? []);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(true);
  const [loading, setLoading] = useState(false);
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const touchStartX = useRef(0);

  const isPaginated = !staticPhotos;

  // Reset when category changes
  useEffect(() => {
    if (isPaginated) {
      setPhotos([]);
      setPage(1);
      setHasNext(true);
    }
  }, [category, isPaginated]);

  // Fetch photos for paginated mode
  const loadMore = useCallback(async () => {
    if (!isPaginated || loading || !hasNext) return;
    setLoading(true);
    try {
      const params: Record<string, string | number> = { page, page_size: 50 };
      if (category) params.scene_category = category;
      const data = await fetchPhotos(params);
      setPhotos((prev) => (page === 1 ? data.items : [...prev, ...data.items]));
      setHasNext(data.has_next);
      setPage((p) => p + 1);
    } catch {
      // Silently fail — error banner shown at page level
    } finally {
      setLoading(false);
    }
  }, [isPaginated, loading, hasNext, page, category]);

  // Initial load
  useEffect(() => {
    if (isPaginated && photos.length === 0 && hasNext) {
      loadMore();
    }
  }, [isPaginated, category]); // eslint-disable-line react-hooks/exhaustive-deps

  // IntersectionObserver for infinite scroll
  useEffect(() => {
    if (!isPaginated || !sentinelRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          loadMore();
        }
      },
      { rootMargin: "200px" }
    );

    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [loadMore, isPaginated]);

  // Lightbox keyboard & swipe
  useEffect(() => {
    if (lightboxIdx === null) return;

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightboxIdx(null);
      if (e.key === "ArrowRight" && lightboxIdx < photos.length - 1)
        setLightboxIdx(lightboxIdx + 1);
      if (e.key === "ArrowLeft" && lightboxIdx > 0)
        setLightboxIdx(lightboxIdx - 1);
    };

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [lightboxIdx, photos.length]);

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0]?.clientX ?? 0;
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (lightboxIdx === null) return;
    const diff = touchStartX.current - (e.changedTouches[0]?.clientX ?? 0);
    if (Math.abs(diff) > 60) {
      if (diff > 0 && lightboxIdx < photos.length - 1) setLightboxIdx(lightboxIdx + 1);
      if (diff < 0 && lightboxIdx > 0) setLightboxIdx(lightboxIdx - 1);
    }
  };

  const activePhoto = lightboxIdx !== null ? photos[lightboxIdx] : null;

  return (
    <>
      <div className="photo-grid">
        {photos.map((photo, idx) => (
          <PhotoCard
            key={photo.id}
            photo={photo}
            onClick={() => setLightboxIdx(idx)}
          />
        ))}
        {/* Skeleton loaders during fetch */}
        {loading &&
          Array.from({ length: 12 }).map((_, i) => (
            <div key={`skel-${i}`} className="photo-card skeleton" />
          ))}
      </div>

      {/* Sentinel for infinite scroll */}
      {isPaginated && hasNext && <div ref={sentinelRef} style={{ height: 1 }} />}

      {loading && (
        <div style={{ display: "flex", justifyContent: "center", padding: "var(--space-6)" }}>
          <div className="spinner" />
        </div>
      )}

      {/* Lightbox */}
      {activePhoto && (
        <div
          className="lightbox"
          onClick={() => setLightboxIdx(null)}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
        >
          <button
            className="lightbox__close"
            onClick={(e) => {
              e.stopPropagation();
              setLightboxIdx(null);
            }}
          >
            ✕
          </button>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            className="lightbox__image"
            src={getPhotoUrl(activePhoto.id)}
            alt={activePhoto.filename}
            onClick={(e) => e.stopPropagation()}
          />
          <div className="lightbox__meta" onClick={(e) => e.stopPropagation()}>
            <div style={{ fontWeight: "var(--weight-semibold)" }}>
              {activePhoto.filename}
            </div>
            <div style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", marginTop: "var(--space-1)" }}>
              {[
                activePhoto.taken_at
                  ? new Date(activePhoto.taken_at).toLocaleDateString()
                  : null,
                [activePhoto.city, activePhoto.country]
                  .filter(Boolean)
                  .join(", ") || null,
                activePhoto.scene_category,
              ]
                .filter(Boolean)
                .join(" · ")}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

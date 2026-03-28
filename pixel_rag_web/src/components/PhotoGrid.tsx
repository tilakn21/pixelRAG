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
  const [libHash, setLibHash] = useState<string>("");
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(true);
  const [loading, setLoading] = useState(false);
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const touchStartX = useRef(0);

  const isPaginated = !staticPhotos;

  // Fetch libHash for cache busting on mount
  useEffect(() => {
    import("@/lib/api").then(api => {
      api.fetchHealth().then(h => setLibHash(h.lib_hash));
    });
  }, []);

  // Sync state with staticPhotos prop (crucial for search updates)
  useEffect(() => {
    if (staticPhotos) {
      setPhotos(staticPhotos);
      setLightboxIdx(null); // Close lightbox if open on new search
    }
  }, [staticPhotos]);

  // Reset when category changes (for paginated mode)
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
      if (diff > 0 && lightboxIdx < photos.length - 1) {
        setLightboxIdx(lightboxIdx + 1);
        setShowDetails(false);
      }
      if (diff < 0 && lightboxIdx > 0) {
        setLightboxIdx(lightboxIdx - 1);
        setShowDetails(false);
      }
    }
  };

  const handleCloseLightbox = () => {
    setLightboxIdx(null);
    setShowDetails(false);
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
            libHash={libHash}
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
          onClick={handleCloseLightbox}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
        >
          <button
            className="lightbox__close"
            onClick={(e) => {
              e.stopPropagation();
              handleCloseLightbox();
            }}
          >
            ✕
          </button>

          <button
            className="lightbox__options"
            onClick={(e) => {
              e.stopPropagation();
              setShowDetails(!showDetails);
            }}
            title="Photo Info"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="12" cy="5" r="1.5" fill="currentColor" />
              <circle cx="12" cy="12" r="1.5" fill="currentColor" />
              <circle cx="12" cy="19" r="1.5" fill="currentColor" />
            </svg>
          </button>

          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            className="lightbox__image"
            src={getPhotoUrl(activePhoto.id, libHash)}
            alt={activePhoto.filename}
            onClick={(e) => e.stopPropagation()}
            style={{ filter: showDetails ? "blur(4px) brightness(0.7)" : "none", transition: "filter 0.3s" }}
          />

          {showDetails && (
            <div className="lightbox__details-panel" onClick={(e) => e.stopPropagation()}>
              <button
                style={{
                  position: "absolute", top: "12px", right: "12px",
                  background: "var(--bg-secondary)", borderRadius: "var(--radius-full)",
                  width: "32px", height: "32px", display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: "18px", color: "var(--text-secondary)", border: "1px solid var(--border-subtle)"
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  setShowDetails(false);
                }}
              >
                ✕
              </button>
              <h2 style={{ marginBottom: "var(--space-8)", fontWeight: "var(--weight-bold)" }}>Memory Details</h2>
              
              <div className="details-row">
                <div className="details-label">Date & Time</div>
                <div className="details-value">
                  {activePhoto.taken_at ? new Date(activePhoto.taken_at).toLocaleString() : "Unknown date"}
                </div>
              </div>

              {(activePhoto.camera_make || activePhoto.camera_model) && (
                <div className="details-row">
                  <div className="details-label">Device Info</div>
                  <div className="details-value">
                    {[activePhoto.camera_make, activePhoto.camera_model].filter(Boolean).join(" ")}
                  </div>
                </div>
              )}

              {activePhoto.person_names && activePhoto.person_names.length > 0 && (
                <div className="details-row">
                  <div className="details-label">People Detected ({activePhoto.person_names.length})</div>
                  <div className="details-value" style={{ marginTop: "4px" }}>
                    {activePhoto.person_names.map(name => (
                      <span key={name} className="people-pill">{name}</span>
                    ))}
                  </div>
                </div>
              )}

              <div className="details-row">
                <div className="details-label">Location</div>
                <div className="details-value">
                  {[activePhoto.city, activePhoto.state, activePhoto.country].filter(Boolean).join(", ") || "No location data"}
                </div>
              </div>

              <div className="details-row">
                <div className="details-label">Scene Intelligence</div>
                <div className="details-value">
                   {activePhoto.scene_category ? (
                     <span style={{ textTransform: "capitalize" }}>{activePhoto.scene_category}</span>
                   ) : "Unclassified"}
                </div>
              </div>

              <div className="details-row">
                <div className="details-label">Local File Path</div>
                <div className="details-value" style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "4px" }}>
                  {activePhoto.path}
                </div>
              </div>
            </div>
          )}

          {!showDetails && (
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
          )}
        </div>
      )}
    </>
  );
}

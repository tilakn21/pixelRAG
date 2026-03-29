"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchHealth, fetchPhotos, getPhotoUrl } from "@/lib/api";
import {
  formatDate,
  formatDateTime,
  formatLocation,
  formatSceneCategory,
} from "@/lib/display";
import type { Photo } from "@/lib/types";
import PhotoCard from "./PhotoCard";

interface PhotoGridProps {
  photos?: Photo[];
  category?: string | null;
}

export default function PhotoGrid({ photos: staticPhotos, category }: PhotoGridProps) {
  const [photos, setPhotos] = useState<Photo[]>(staticPhotos ?? []);
  const [libHash, setLibHash] = useState("");
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(true);
  const [loading, setLoading] = useState(false);
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const touchStartX = useRef(0);
  const isPaginated = !staticPhotos;

  const loadPage = useCallback(
    async (targetPage: number, replace: boolean) => {
      if (!isPaginated) return;

      setLoading(true);
      try {
        const params: Record<string, string | number> = {
          page: targetPage,
          page_size: 50,
        };

        if (category) {
          params.scene_category = category;
        }

        const data = await fetchPhotos(params);
        setPhotos((current) => (replace ? data.items : [...current, ...data.items]));
        setHasNext(data.has_next);
        setPage(targetPage + 1);
      } finally {
        setLoading(false);
      }
    },
    [category, isPaginated]
  );

  const loadMore = useCallback(async () => {
    if (!isPaginated || loading || !hasNext) return;
    await loadPage(page, false);
  }, [hasNext, isPaginated, loadPage, loading, page]);

  useEffect(() => {
    fetchHealth()
      .then((health) => setLibHash(health.lib_hash))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!staticPhotos) return;
    setPhotos(staticPhotos);
    setLightboxIdx(null);
    setShowDetails(false);
  }, [staticPhotos]);

  useEffect(() => {
    if (!isPaginated) return;
    setPhotos([]);
    setPage(1);
    setHasNext(true);
    void loadPage(1, true);
  }, [category, isPaginated, loadPage]);

  useEffect(() => {
    if (!isPaginated || !sentinelRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          void loadMore();
        }
      },
      { rootMargin: "240px" }
    );

    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [isPaginated, loadMore]);

  useEffect(() => {
    if (lightboxIdx === null) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setLightboxIdx(null);
        setShowDetails(false);
      }

      if (event.key === "ArrowRight" && lightboxIdx < photos.length - 1) {
        setLightboxIdx(lightboxIdx + 1);
      }

      if (event.key === "ArrowLeft" && lightboxIdx > 0) {
        setLightboxIdx(lightboxIdx - 1);
      }
    };

    window.addEventListener("keydown", handleKey);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKey);
    };
  }, [lightboxIdx, photos.length]);

  const activePhoto = lightboxIdx !== null ? photos[lightboxIdx] : null;

  const handleTouchStart = (event: React.TouchEvent) => {
    touchStartX.current = event.touches[0]?.clientX ?? 0;
  };

  const handleTouchEnd = (event: React.TouchEvent) => {
    if (lightboxIdx === null) return;
    const diff = touchStartX.current - (event.changedTouches[0]?.clientX ?? 0);

    if (Math.abs(diff) < 64) return;

    if (diff > 0 && lightboxIdx < photos.length - 1) {
      setLightboxIdx(lightboxIdx + 1);
    }

    if (diff < 0 && lightboxIdx > 0) {
      setLightboxIdx(lightboxIdx - 1);
    }
  };

  if (!loading && photos.length === 0) {
    return (
      <div className="void-state">
        <span className="panel__title">No Images In View</span>
        <h2 className="panel__heading">This chapter is currently empty.</h2>
        <p>Try a broader category, run a sync, or search with a different cue.</p>
      </div>
    );
  }

  return (
    <>
      <div className="photo-grid--masonry">
        {photos.map((photo, index) => (
          <PhotoCard
            key={photo.id}
            photo={photo}
            onClick={() => {
              setLightboxIdx(index);
              setShowDetails(false);
            }}
            libHash={libHash}
          />
        ))}

        {loading
          ? Array.from({ length: 8 }).map((_, index) => (
              <div
                key={`skeleton-${index}`}
                className="photo-card skeleton"
                style={{ minHeight: 220 + (index % 4) * 54 }}
              />
            ))
          : null}
      </div>

      {isPaginated && hasNext ? <div ref={sentinelRef} style={{ height: 1 }} /> : null}

      {loading && photos.length > 0 ? (
        <div style={{ display: "flex", justifyContent: "center", paddingTop: 24 }}>
          <div className="spinner" />
        </div>
      ) : null}

      {activePhoto ? (
        <div className="lightbox" onClick={() => setLightboxIdx(null)}>
          <button
            type="button"
            className="lightbox__close"
            onClick={() => {
              setLightboxIdx(null);
              setShowDetails(false);
            }}
          >
            <span className="visually-hidden">Close lightbox</span>
            ×
          </button>

          <button
            type="button"
            className="lightbox__toggle"
            onClick={(event) => {
              event.stopPropagation();
              setShowDetails((value) => !value);
            }}
          >
            <span className="visually-hidden">Toggle details</span>
            i
          </button>

          {lightboxIdx !== null && lightboxIdx > 0 ? (
            <button
              type="button"
              className="lightbox__nav lightbox__nav--prev"
              style={{ background: "#000", color: "#fff", border: "var(--border-thick)", borderRadius: "12px", width: "48px", height: "48px", fontSize: "1.5rem", display: "flex", alignItems: "center", justifyContent: "center" }}
              onClick={(event) => {
                event.stopPropagation();
                setLightboxIdx(lightboxIdx - 1);
              }}
            >
              <span className="visually-hidden">Previous image</span>
              ←
            </button>
          ) : null}

          {lightboxIdx !== null && lightboxIdx < photos.length - 1 ? (
            <button
              type="button"
              className="lightbox__nav lightbox__nav--next"
              style={{ background: "#000", color: "#fff", border: "var(--border-thick)", borderRadius: "12px", width: "48px", height: "48px", fontSize: "1.5rem", display: "flex", alignItems: "center", justifyContent: "center" }}
              onClick={(event) => {
                event.stopPropagation();
                setLightboxIdx(lightboxIdx + 1);
              }}
            >
              <span className="visually-hidden">Next image</span>
              →
            </button>
          ) : null}

          <div
            className="lightbox__content"
            style={{ gridTemplateColumns: showDetails ? undefined : "1fr" }}
            onClick={(event) => event.stopPropagation()}
          >
            <div
              className="lightbox__image-wrap"
              onTouchStart={handleTouchStart}
              onTouchEnd={handleTouchEnd}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                className="lightbox__image"
                src={getPhotoUrl(activePhoto.id, libHash)}
                alt={activePhoto.filename}
              />

              {!showDetails ? (
                <div className="lightbox__meta" style={{ background: "rgba(0,0,0,0.85)", backdropFilter: "blur(8px)", padding: "16px 20px", borderTop: "var(--border-thick)" }}>
                  <strong style={{ fontFamily: "var(--font-pixel)", fontSize: "1.2rem", textTransform: "uppercase", display: "block", marginBottom: "4px" }}>{activePhoto.filename.toUpperCase()}</strong>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.8, textTransform: "uppercase" }}>
                    {[
                      formatDate(activePhoto.taken_at),
                      formatLocation([activePhoto.city, activePhoto.country]),
                      formatSceneCategory(activePhoto.scene_category),
                    ].join(" // ")}
                  </span>
                </div>
              ) : null}
            </div>

            {showDetails ? (
              <aside className="lightbox__details">
                <div style={{ marginBottom: "32px" }}>
                  <span className="panel__title" style={{ fontFamily: "var(--font-pixel)", fontSize: "0.7rem" }}>[ INTEL_NODE ]</span>
                  <h2 className="panel__heading" style={{ fontFamily: "var(--font-pixel)", fontSize: "1.8rem", textTransform: "uppercase", margin: "8px 0" }}>{activePhoto.filename}</h2>
                </div>

                {/* Section: AI Analysis */}
                <div className="detail-card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span className="lightbox__label" style={{ margin: 0 }}>AI Confidence</span>
                    <span style={{ fontFamily: "var(--font-pixel)", color: "var(--electric-purple)" }}>{(activePhoto.scene_confidence || 0 * 100).toFixed(1)}%</span>
                  </div>
                  <div className="confidence-meter">
                    <div className="confidence-bar" style={{ width: `${(activePhoto.scene_confidence || 0) * 100}%` }} />
                  </div>
                  
                  {activePhoto.scene_tags.length > 0 ? (
                    <div className="tag-flow">
                      {activePhoto.scene_tags.map(tag => (
                        <span key={tag} className="tag-pill">#{tag}</span>
                      ))}
                    </div>
                  ) : null}
                </div>

                {/* Section: Description */}
                {activePhoto.description ? (
                  <div className="detail-card">
                    <span className="lightbox__label">AI Description</span>
                    <p style={{ margin: "8px 0 0 0", fontSize: "0.9rem", lineHeight: "1.5", color: "var(--obsidian)" }}>
                      {activePhoto.description}
                    </p>
                  </div>
                ) : null}

                {/* Section: Identities */}
                {activePhoto.person_names.length > 0 ? (
                  <div className="detail-card" style={{ background: "var(--sun-yellow)" }}>
                    <span className="lightbox__label">Resolved Identities</span>
                    <div className="pill-stack" style={{ marginTop: "8px" }}>
                      {activePhoto.person_names.map((name) => (
                        <span key={name} className="meta-pill" style={{ background: "#000", color: "#fff" }}>
                          {name}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                {/* Section: Location */}
                <div className="detail-card">
                  <span className="lightbox__label">Geolocation</span>
                  <p style={{ margin: "8px 0", fontSize: "0.95rem", fontWeight: "bold" }}>
                    {formatLocation([activePhoto.city, activePhoto.state, activePhoto.country])}
                  </p>
                  {activePhoto.latitude && activePhoto.longitude ? (
                    <div style={{ marginTop: "12px", display: "flex", gap: "10px", alignItems: "center" }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.7rem" }}>{activePhoto.latitude.toFixed(4)}, {activePhoto.longitude.toFixed(4)}</span>
                      <a 
                        href={`https://www.google.com/maps?q=${activePhoto.latitude},${activePhoto.longitude}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn-brutalist"
                        style={{ padding: "4px 10px", fontSize: "0.6rem", background: "var(--electric-blue)", color: "#fff" }}
                      >
                        NAVIGATE_GLOBAL
                      </a>
                    </div>
                  ) : null}
                </div>

                {/* Section: Technical Meta */}
                <div className="detail-card" style={{ background: "rgba(0,0,0,0.03)" }}>
                  <div className="lightbox__row">
                    <span className="lightbox__label">Capture Time</span>
                    <span className="lightbox__value">{formatDateTime(activePhoto.taken_at)}</span>
                  </div>
                  <div className="lightbox__row">
                    <span className="lightbox__label">Device</span>
                    <span className="lightbox__value">
                      {[activePhoto.camera_make, activePhoto.camera_model].filter(Boolean).join(" ") || "UNKNOWN_HARDWARE"}
                    </span>
                  </div>
                  <div style={{ marginTop: "12px" }}>
                    <span className="lightbox__label">System Path</span>
                    <div style={{ wordBreak: "break-all", fontFamily: "var(--font-mono)", fontSize: "0.65rem", opacity: 0.6, marginTop: "4px" }}>
                      {activePhoto.path}
                    </div>
                  </div>
                </div>
              </aside>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}

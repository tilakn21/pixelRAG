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
        setShowDetails(false);
      }

      if (event.key === "ArrowLeft" && lightboxIdx > 0) {
        setLightboxIdx(lightboxIdx - 1);
        setShowDetails(false);
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
      setShowDetails(false);
    }

    if (diff < 0 && lightboxIdx > 0) {
      setLightboxIdx(lightboxIdx - 1);
      setShowDetails(false);
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
      <div className="photo-grid">
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
              onClick={(event) => {
                event.stopPropagation();
                setLightboxIdx(lightboxIdx - 1);
                setShowDetails(false);
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
              onClick={(event) => {
                event.stopPropagation();
                setLightboxIdx(lightboxIdx + 1);
                setShowDetails(false);
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
                <div className="lightbox__meta">
                  <strong>{activePhoto.filename}</strong>
                  <span>
                    {[
                      formatDate(activePhoto.taken_at),
                      formatLocation([activePhoto.city, activePhoto.country]),
                      formatSceneCategory(activePhoto.scene_category),
                    ].join(" · ")}
                  </span>
                </div>
              ) : null}
            </div>

            {showDetails ? (
              <aside className="lightbox__details">
                <div>
                  <span className="panel__title">Memory Details</span>
                  <h2 className="panel__heading">{activePhoto.filename}</h2>
                </div>

                <div className="lightbox__row">
                  <span className="lightbox__label">Captured</span>
                  <span className="lightbox__value">{formatDateTime(activePhoto.taken_at)}</span>
                </div>

                <div className="lightbox__row">
                  <span className="lightbox__label">Location</span>
                  <span className="lightbox__value">
                    {formatLocation([activePhoto.city, activePhoto.state, activePhoto.country])}
                  </span>
                </div>

                <div className="lightbox__row">
                  <span className="lightbox__label">Scene</span>
                  <span className="lightbox__value">
                    {formatSceneCategory(activePhoto.scene_category)}
                  </span>
                </div>

                {(activePhoto.camera_make || activePhoto.camera_model) ? (
                  <div className="lightbox__row">
                    <span className="lightbox__label">Device</span>
                    <span className="lightbox__value">
                      {[activePhoto.camera_make, activePhoto.camera_model].filter(Boolean).join(" ")}
                    </span>
                  </div>
                ) : null}

                {activePhoto.person_names.length > 0 ? (
                  <div className="lightbox__row">
                    <span className="lightbox__label">Identities</span>
                    <div className="pill-stack">
                      {activePhoto.person_names.map((name) => (
                        <span key={name} className="meta-pill">
                          {name}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className="lightbox__row">
                  <span className="lightbox__label">Local Path</span>
                  <span className="lightbox__value mono">{activePhoto.path}</span>
                </div>
              </aside>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}

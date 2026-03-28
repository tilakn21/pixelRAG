// pixel_rag_web/src/app/people/[id]/page.tsx
"use client";

import { use, useEffect, useState } from "react";
import { fetchPerson, fetchPhotos } from "@/lib/api";
import type { Person, Photo } from "@/lib/types";
import PhotoGrid from "@/components/PhotoGrid";
import Link from "next/link";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function PersonPhotosPage({ params }: PageProps) {
  const { id } = use(params);
  const personId = parseInt(id);

  const [person, setPerson] = useState<Person | null>(null);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const [personData, photosData] = await Promise.all([
          fetchPerson(personId),
          fetchPhotos({ person_id: personId, page_size: 200 }),
        ]);
        setPerson(personData);
        setPhotos(photosData.items);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load person data");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [personId]);

  if (loading) {
    return (
      <div style={{ paddingTop: "var(--space-8)" }}>
        <div className="skeleton" style={{ height: 40, width: 300, marginBottom: "var(--space-4)" }} />
        <div className="photo-grid">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="photo-card skeleton" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !person) {
    return (
      <div className="empty-state">
        <div className="empty-state__title">Error</div>
        <div className="empty-state__desc">{error || "Person not found"}</div>
        <Link href="/people" className="btn btn--primary" style={{ marginTop: "var(--space-4)" }}>
          Back to People
        </Link>
      </div>
    );
  }

  return (
    <div style={{ paddingTop: "var(--space-6)" }}>
      <header style={{ marginBottom: "var(--space-6)" }}>
        <Link 
          href="/people" 
          style={{ 
            color: "var(--text-tertiary)", 
            fontSize: "var(--text-sm)", 
            display: "flex", 
            alignItems: "center", 
            gap: "var(--space-1)",
            marginBottom: "var(--space-2)"
          }}
        >
          ← Back to People
        </Link>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
          {person.cover_face_url && (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${person.cover_face_url}`}
              alt={person.name ?? "person"}
              style={{
                width: 64,
                height: 64,
                borderRadius: "50%",
                objectFit: "cover",
                border: "2px solid var(--glass-border)"
              }}
            />
          )}
          <div>
            <h1 className="page-title">{person.name || "Unnamed Person"}</h1>
            <p className="page-subtitle">
              {person.face_count} photo{person.face_count !== 1 ? "s" : ""} identified
            </p>
          </div>
        </div>
      </header>

      {photos.length > 0 ? (
        <PhotoGrid photos={photos} />
      ) : (
        <div className="empty-state">
          <div className="empty-state__title">No photos found</div>
          <div className="empty-state__desc">This is unexpected. No photos are linked to this person cluster.</div>
        </div>
      )}
    </div>
  );
}

"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import PhotoGrid from "@/components/PhotoGrid";
import { deletePerson, fetchPerson, fetchPhotos } from "@/lib/api";
import { formatPurityScore } from "@/lib/display";
import type { Person, Photo } from "@/lib/types";
import { useRouter } from "next/navigation";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function PersonPhotosPage({ params }: PageProps) {
  const { id } = use(params);
  const personId = Number.parseInt(id, 10);
  const [person, setPerson] = useState<Person | null>(null);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

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
      } catch (caughtError) {
        setError(caughtError instanceof Error ? caughtError.message : "Failed to load this cluster.");
      } finally {
        setLoading(false);
      }
    }

    void loadData();
  }, [personId]);

  const handleDelete = async () => {
    if (!window.confirm(`Dissolve "${person?.name || "this cluster"}"? Photos will remain, but the identity link will be removed.`)) {
      return;
    }

    setIsDeleting(true);
    try {
      await deletePerson(personId);
      router.push("/people");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Failed to dissolve the cluster.");
      setIsDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="route">
        <div className="detail-hero skeleton" style={{ minHeight: 240 }} />
        <div className="photo-grid">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="photo-card skeleton" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !person) {
    return (
      <div className="route">
        <div className="void-state">
          <span className="panel__title">Cluster Unavailable</span>
          <h2 className="panel__heading">This identity could not be loaded.</h2>
          <p>{error || "The requested person was not found."}</p>
          <Link href="/people" className="button button--primary">
            Back to people
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="route">
      <Link href="/people" className="button button--ghost" style={{ width: "fit-content" }}>
        Back to people
      </Link>

      <section className="detail-hero">
        <div className="detail-hero__header">
          <div className="person-card__lead">
            <div className="detail-hero__portrait">
              {person.cover_face_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${person.cover_face_url}`}
                  alt={person.name ?? "Unnamed person"}
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              ) : null}
            </div>

            <div className="detail-hero__identity">
              <span className="panel__title">Identity Chapter</span>
              <h1 className="page-title" style={{ fontSize: "clamp(2.4rem, 2rem + 1vw, 3.4rem)" }}>
                {person.name || "Unnamed person"}
              </h1>
              <span className="detail-hero__meta">
                {person.face_count} linked photo{person.face_count === 1 ? "" : "s"} · {formatPurityScore(person.purity_score)}
              </span>
            </div>
          </div>

          <button
            type="button"
            className="button button--danger"
            disabled={isDeleting}
            onClick={() => void handleDelete()}
          >
            {isDeleting ? "Dissolving" : "Dissolve cluster"}
          </button>
        </div>

        <div className="detail-hero__facts">
          <span className="meta-pill">Cluster review surface</span>
          <span className="meta-pill">Linked memories · {photos.length}</span>
          <span className="meta-pill">Identity refinement tools live on the roster</span>
        </div>
      </section>

      {photos.length > 0 ? (
        <PhotoGrid photos={photos} />
      ) : (
        <div className="void-state">
          <span className="panel__title">No Linked Frames</span>
          <h2 className="panel__heading">This identity currently has no visible photos.</h2>
          <p>That usually means the cluster was recently modified and needs a fresh sync or review pass.</p>
        </div>
      )}
    </div>
  );
}

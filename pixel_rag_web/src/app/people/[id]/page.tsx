"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import PhotoGrid from "@/components/PhotoGrid";
import { deletePerson, fetchPerson, fetchPhotos, fetchHealth } from "@/lib/api";
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
  const [libHash, setLibHash] = useState("");
  const router = useRouter();

  useEffect(() => {
    fetchHealth()
      .then((health) => setLibHash(`${health.lib_hash}_${health.sync_version}`))
      .catch(() => {});
  }, []);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);

      try {
        const [personData, photosData] = await Promise.all([
          fetchPerson(personId, libHash),
          fetchPhotos({ person_id: personId, page_size: 200, libHash }),
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
  }, [personId, libHash]);

  const handleDelete = async () => {
    if (!window.confirm(`Dissolve "${person?.name || "this cluster"}"? Photos will remain, but the identity link will be removed.`)) {
      return;
    }

    setIsDeleting(true);
    try {
      await deletePerson(personId, libHash);
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
      <div className="bento-container" style={{ padding: "40px 0" }}>
        <div className="panel" style={{ background: "var(--sun-yellow)", textAlign: "center", padding: "60px 20px" }}>
          <span className="panel__title" style={{ fontFamily: "var(--font-pixel)" }}>[ CLUSTER_UNAVAILABLE ]</span>
          <h2 className="panel__heading" style={{ fontFamily: "var(--font-pixel)", fontSize: "2rem", margin: "12px 0" }}>IDENTITY_RESOLUTION_FAILED</h2>
          <p style={{ maxWidth: "500px", margin: "0 auto", opacity: 0.6 }}>{error || "The requested person was not found."}</p>
          <Link href="/people" className="button button--primary" style={{ marginTop: "24px", borderRadius: "12px" }}>
            BACK_TO_PEOPLE
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="bento-container" style={{ display: "grid", gap: "20px", gridTemplateColumns: "repeat(12, 1fr)", padding: "20px 0" }}>
      {/* Navigation & Actions */}
      <div style={{ gridColumn: "span 12", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Link href="/people" className="button button--secondary" style={{ borderRadius: "12px", border: "var(--border-thick)" }}>
          &lt;&lt; BACK_TO_PEOPLE
        </Link>
        <button
          type="button"
          className="button button--secondary"
          style={{ borderRadius: "12px", border: "var(--border-thick)", background: "transparent" }}
          disabled={isDeleting}
          onClick={() => void handleDelete()}
        >
          {isDeleting ? "DISSOLVING..." : "DISSOLVE_CLUSTER"}
        </button>
      </div>

      {/* Person Hero */}
      <article className="panel" style={{ gridColumn: "span 8", background: "var(--electric-purple)", color: "#fff", minHeight: "360px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div className="title-block">
          <span className="eyebrow" style={{ fontFamily: "var(--font-pixel)", color: "var(--sun-yellow)" }}>[ IDENTITY_CHAPTER ]</span>
          <h1 className="page-title" style={{ fontFamily: "var(--font-pixel)", fontSize: "var(--text-3xl)", textTransform: "uppercase", margin: "8px 0" }}>
            {person.name || "UNNAMED_PERSON"}
          </h1>
          <p className="page-subtitle" style={{ fontSize: "var(--text-lg)", maxWidth: "500px", opacity: 0.9 }}>
             Reviewing {person.face_count} linked memories across the archive. Identity refinement remains a deliberate, visual process.
          </p>
          <div style={{ marginTop: "24px", fontFamily: "var(--font-mono)", fontSize: "0.8rem", textTransform: "uppercase", opacity: 0.7 }}>
             SIGNAL_STRENGTH: {formatPurityScore(person.purity_score)} • CLUSTER_INTEGRITY: STABLE
          </div>
        </div>
      </article>

      {/* Portrait Card */}
      <article className="panel" style={{ gridColumn: "span 4", padding: "0", background: "var(--obsidian)", overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center" }}>
        {person.cover_face_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}${person.cover_face_url}`}
            alt={person.name ?? "Unnamed person"}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
           <div style={{ fontFamily: "var(--font-pixel)", color: "var(--sun-yellow)", fontSize: "1rem" }}>NO_SIGNAL_IMAGE</div>
        )}
      </article>

      {/* Marquee Ticker */}
      <article className="panel" style={{ gridColumn: "span 12", background: "var(--obsidian)", color: "#fff", padding: "0", display: "flex", alignItems: "center", overflow: "hidden", height: "60px" }}>
        <div className="marquee" style={{ whiteSpace: "nowrap", fontSize: "1.5rem", fontFamily: "var(--font-pixel)" }}>
          <div className="marquee-content" style={{ display: "inline-block", paddingLeft: "100%", animation: "marquee 30s linear infinite" }}>
            IDENTITY RESOLUTION: ACTIVE • RECOGNITION NODE: STABLE • MAPPING FACE CLUSTERS • PIXELRAG ANALYSIS PASS COMPLETED • 
          </div>
        </div>
      </article>

      {photos.length > 0 ? (
        <div style={{ gridColumn: "span 12" }}>
           <PhotoGrid photos={photos} />
        </div>
      ) : (
        <div className="panel" style={{ gridColumn: "span 12", background: "#f8f8f8", textAlign: "center", padding: "60px 20px" }}>
          <span className="panel__title" style={{ fontFamily: "var(--font-pixel)" }}>[ NO_LINKED_FRAMES ]</span>
          <h2 className="panel__heading" style={{ fontFamily: "var(--font-pixel)", fontSize: "2rem", margin: "12px 0" }}>EMPTY_SEQUENCE</h2>
          <p style={{ maxWidth: "500px", margin: "0 auto", opacity: 0.6 }}>That usually means the cluster was recently modified and needs a fresh sync or review pass.</p>
        </div>
      )}
    </div>
  );
}

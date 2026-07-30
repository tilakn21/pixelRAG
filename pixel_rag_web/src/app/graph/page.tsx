"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import * as THREE from "three";
import SpriteText from "three-spritetext";
import TopNav from "@/components/TopNav";
import { fetchHealth, fetchIdentities, fetchPhotos, getPhotoUrl } from "@/lib/api";
import type { Photo } from "@/lib/types";

// ── Constants ─────────────────────────────────────────────────────────
const CONFIRMED_COLOR = new THREE.Color("#FFD700");   // Warm gold
const UNCONFIRMED_COLOR = new THREE.Color("#7B68EE");  // Cool purple
const LINK_COLORS = {
  low: "#3b4d7a",    // dim blue-gray
  mid: "#7c5cbf",    // warm purple
  high: "#e8b931",   // golden
};

function getNodeSize(faceCount: number): number {
  const min = 18, max = 42;
  const clamped = Math.min(Math.max(faceCount, 2), 200);
  return min + (max - min) * (Math.log(clamped) / Math.log(200));
}

function getLinkColor(weight: number): string {
  if (weight >= 11) return LINK_COLORS.high;
  if (weight >= 4) return LINK_COLORS.mid;
  return LINK_COLORS.low;
}

function getLinkWidth(weight: number): number {
  if (weight >= 11) return 1.8;
  if (weight >= 4) return 1.0;
  return 0.4;
}

function getLinkOpacity(weight: number): number {
  if (weight >= 11) return 0.5;
  if (weight >= 4) return 0.3;
  return 0.12;
}

// ── Component ─────────────────────────────────────────────────────────
export default function GraphPage() {
  const [graphData, setGraphData] = useState<{ nodes: any[]; links: any[] }>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const graphInstanceRef = useRef<any>(null);
  const [libHash, setLibHash] = useState("");

  // Interaction
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [hoveredNode, setHoveredNode] = useState<any>(null);
  const [sidebarPhotos, setSidebarPhotos] = useState<Photo[]>([]);
  const [loadingPhotos, setLoadingPhotos] = useState(false);
  const [activePhoto, setActivePhoto] = useState<Photo | null>(null);

  // High performance overlay tracking
  const overlayRef = useRef<HTMLDivElement>(null);
  const activeHoverNodeRef = useRef<any>(null);

  // Idle drift
  const idleDriftRef = useRef<number | null>(null);
  const lastInteractionRef = useRef(Date.now());

  // Keep ref in sync for animation loop
  useEffect(() => {
    activeHoverNodeRef.current = hoveredNode;
  }, [hoveredNode]);

  useEffect(() => {
    fetchHealth()
      .then((health) => setLibHash(`${health.lib_hash}_${health.sync_version}`))
      .catch(() => {});
  }, []);

  // ── Data Fetching ───────────────────────────────────────────────────
  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const sp = libHash ? `?h=${libHash}` : "";
        const response = await fetch(`/api/identities/graph${sp}`);
        if (!response.ok) throw new Error("Failed to fetch graph data");
        const data = await response.json();
        setGraphData(data);
      } catch (err) {
        console.error("Error loading graph:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [libHash]);

  // ── Camera Controls ─────────────────────────────────────────────────
  const zoomIn = useCallback(() => {
    if (!graphInstanceRef.current) return;
    lastInteractionRef.current = Date.now();
    const g = graphInstanceRef.current;
    const pos = g.cameraPosition();
    const mag = Math.hypot(pos.x, pos.y, pos.z);
    if (mag < 80) return;
    const ratio = 0.75;
    g.cameraPosition(
      { x: pos.x * ratio, y: pos.y * ratio, z: pos.z * ratio },
      { x: 0, y: 0, z: 0 }, 400
    );
  }, []);

  const zoomOut = useCallback(() => {
    if (!graphInstanceRef.current) return;
    lastInteractionRef.current = Date.now();
    const g = graphInstanceRef.current;
    const pos = g.cameraPosition();
    const mag = Math.hypot(pos.x, pos.y, pos.z);
    if (mag > 1500) return;
    const ratio = 1.35;
    g.cameraPosition(
      { x: pos.x * ratio, y: pos.y * ratio, z: pos.z * ratio },
      { x: 0, y: 0, z: 0 }, 400
    );
  }, []);

  const resetView = useCallback(() => {
    if (!graphInstanceRef.current) return;
    lastInteractionRef.current = Date.now();
    graphInstanceRef.current.cameraPosition(
      { x: 0, y: 0, z: 600 },
      { x: 0, y: 0, z: 0 }, 800
    );
  }, []);

  // ── 3D Force Graph ──────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || graphData.nodes.length === 0) return;

    let active = true;

    // Create shared alpha map once for circular thumbnails
    const alphaCanvas = document.createElement("canvas");
    alphaCanvas.width = 128;
    alphaCanvas.height = 128;
    const actx = alphaCanvas.getContext("2d")!;
    actx.fillStyle = "#000";
    actx.fillRect(0, 0, 128, 128);
    actx.fillStyle = "#FFF";
    actx.beginPath();
    actx.arc(64, 64, 64, 0, Math.PI * 2);
    actx.fill();
    const sharedAlphaMap = new THREE.CanvasTexture(alphaCanvas);

    import("3d-force-graph").then((ForceGraph3DModule) => {
      if (!active || !containerRef.current) return;
      const ForceGraph3D = ForceGraph3DModule.default as any;

      if (!graphInstanceRef.current) {
        const graph = ForceGraph3D()(containerRef.current!)
          .graphData(graphData)
          .backgroundColor("rgba(0,0,0,0)")
          .showNavInfo(false)

          // ── Links — Memory Threads ────────────────────────────────
          .linkColor((link: any) => getLinkColor(link.weight || 1))
          .linkOpacity(0.25)
          .linkWidth((link: any) => getLinkWidth(link.weight || 1))
          .linkCurvature(0.15)
          .linkCurveRotation((link: any) => link.weight * 0.3)
          .linkDirectionalParticles((link: any) => {
            const w = link.weight || 1;
            return w >= 11 ? 4 : w >= 4 ? 2 : 1;
          })
          .linkDirectionalParticleWidth(1.5)
          .linkDirectionalParticleSpeed(0.004)
          .linkDirectionalParticleColor((link: any) => {
            const w = link.weight || 1;
            return w >= 11 ? "#ffd700" : w >= 4 ? "#a78bfa" : "#4a6fa5";
          })

          // ── Nodes — Memory Orbs with Optimized Thumbnails ───────────────────────────────────
          .nodeThreeObject((node: any) => {
            if (node.__threeObj) return node.__threeObj;

            const group = new THREE.Group();
            const size = getNodeSize(node.face_count || 2);
            const glowColor = node.confirmed ? CONFIRMED_COLOR : UNCONFIRMED_COLOR;

            // -- Outer glow ring (additive blended)
            const ringGeo = new THREE.RingGeometry(size * 0.52, size * 0.58, 48);
            const ringMat = new THREE.MeshBasicMaterial({
              color: glowColor,
              transparent: true,
              opacity: 0.5,
              side: THREE.DoubleSide,
              blending: THREE.AdditiveBlending,
              depthWrite: false,
            });
            const ring = new THREE.Mesh(ringGeo, ringMat);
            group.add(ring);

            // -- Soft halo glow behind node
            const haloGeo = new THREE.CircleGeometry(size * 0.7, 48);
            const haloMat = new THREE.MeshBasicMaterial({
              color: glowColor,
              transparent: true,
              opacity: 0.08,
              side: THREE.DoubleSide,
              blending: THREE.AdditiveBlending,
              depthWrite: false,
            });
            const halo = new THREE.Mesh(haloGeo, haloMat);
            halo.position.z = -1;
            group.add(halo);

            // -- Face photo sprite (ultra-fast TextureLoader with alpha mask)
            const spriteMat = new THREE.SpriteMaterial({
              color: 0xffffff,
              transparent: true,
              alphaMap: sharedAlphaMap,
              alphaTest: 0.1
            });
            const sprite = new THREE.Sprite(spriteMat);
            sprite.scale.set(size, size, 1);
            group.add(sprite);

            if (node.cover_face_url) {
              const loader = new THREE.TextureLoader();
              loader.setCrossOrigin("anonymous");
              loader.load(node.cover_face_url, (texture) => {
                texture.minFilter = THREE.LinearFilter;
                spriteMat.map = texture;
                spriteMat.needsUpdate = true;
              });
            }

            node.__threeObj = group;
            return group;
          })

          // ── Interactions ──────────────────────────────────────────
          .onNodeHover((node: any) => {
            if (containerRef.current) {
              containerRef.current.style.cursor = node ? "pointer" : "default";
            }
            setHoveredNode(node || null);
          })
          .onNodeClick(async (node: any) => {
            lastInteractionRef.current = Date.now();
            const distance = 180;
            const distRatio =
              1 + distance / Math.hypot(node.x, node.y, node.z);
            graph.cameraPosition(
              {
                x: node.x * distRatio,
                y: node.y * distRatio,
                z: node.z * distRatio,
              },
              node,
              1200
            );
            setSelectedNode(node);
            setLoadingPhotos(true);
            setSidebarPhotos([]);
            try {
              const data = await fetchPhotos({
                person_id: node.id,
                page_size: 50,
                libHash,
              });
              if (active) setSidebarPhotos(data.items);
            } catch (err) {
              console.error(err);
            } finally {
              if (active) setLoadingPhotos(false);
            }
          });

        // ── Physics ──────────────────────────────────────────────────
        graph.d3Force("charge").strength(-800);
        graph.d3Force("link").distance(220);

        // ── Atmosphere — Layered Starfield ───────────────────────────
        // Layer 1: Distant dim stars
        const starGeo1 = new THREE.BufferGeometry();
        const starPos1 = new Float32Array(8000 * 3);
        for (let i = 0; i < 8000 * 3; i++)
          starPos1[i] = (Math.random() - 0.5) * 5000;
        starGeo1.setAttribute(
          "position",
          new THREE.BufferAttribute(starPos1, 3)
        );
        graph.scene().add(
          new THREE.Points(
            starGeo1,
            new THREE.PointsMaterial({
              size: 0.8,
              color: 0x6677aa,
              transparent: true,
              opacity: 0.4,
              blending: THREE.AdditiveBlending,
              depthWrite: false,
            })
          )
        );

        // Layer 2: Bright close stars (twinkling)
        const starGeo2 = new THREE.BufferGeometry();
        const starPos2 = new Float32Array(300 * 3);
        for (let i = 0; i < 300 * 3; i++)
          starPos2[i] = (Math.random() - 0.5) * 3000;
        starGeo2.setAttribute(
          "position",
          new THREE.BufferAttribute(starPos2, 3)
        );
        const brightStars = new THREE.Points(
          starGeo2,
          new THREE.PointsMaterial({
            size: 2.5,
            color: 0xccddff,
            transparent: true,
            opacity: 0.7,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
          })
        );
        graph.scene().add(brightStars);

        // ── Animation Loop — Tracking + Idle Drift ─────────────────
        let frameId: number;
        const clock = new THREE.Clock();
        const animate = () => {
          frameId = requestAnimationFrame(animate);
          const elapsed = clock.getElapsedTime();

          // Twinkle bright stars
          if (brightStars.material instanceof THREE.PointsMaterial) {
            brightStars.material.opacity =
              0.5 + 0.3 * Math.sin(elapsed * 0.7);
          }
          
          // High performance overlay tracking
          if (activeHoverNodeRef.current && overlayRef.current && graph) {
            try {
              const coords = graph.graph2ScreenCoords(
                activeHoverNodeRef.current.x, 
                activeHoverNodeRef.current.y, 
                activeHoverNodeRef.current.z
              );
              overlayRef.current.style.transform = `translate(${coords.x}px, ${coords.y}px)`;
              overlayRef.current.style.opacity = '1';
            } catch (e) {
               // Ignore errors if node goes out of bounds briefly
            }
          } else if (overlayRef.current) {
            overlayRef.current.style.opacity = '0';
          }

          // Idle camera drift (after 5s of no interaction)
          const idle = Date.now() - lastInteractionRef.current;
          if (idle > 5000) {
            const pos = graph.cameraPosition();
            const mag = Math.hypot(pos.x, pos.y, pos.z);
            if (mag > 0) {
              const angle = elapsed * 0.03;
              const driftX = Math.cos(angle) * mag * 0.002;
              const driftY = Math.sin(angle * 0.7) * mag * 0.001;
              graph.cameraPosition({
                x: pos.x + driftX,
                y: pos.y + driftY,
                z: pos.z,
              });
            }
          }
        };
        animate();

        graphInstanceRef.current = graph;

        // Cleanup on unmount for fast-refresh
        return () => {
          active = false;
          if (frameId) cancelAnimationFrame(frameId);
          if (graphInstanceRef.current) {
             graphInstanceRef.current._destructor && graphInstanceRef.current._destructor();
             graphInstanceRef.current = null;
             if (containerRef.current) {
               containerRef.current.innerHTML = '';
             }
          }
        };
      }
    });

    return () => {
      active = false;
    };
  }, [graphData, libHash]);

  // Track mouse/touch for idle detection
  useEffect(() => {
    const handler = () => {
      lastInteractionRef.current = Date.now();
    };
    window.addEventListener("mousemove", handler);
    window.addEventListener("wheel", handler);
    return () => {
      window.removeEventListener("mousemove", handler);
      window.removeEventListener("wheel", handler);
    };
  }, []);

  // ── Loading State ────────────────────────────────────────────────────
  if (loading) {
    return (
      <main className="layout realm-bg" style={{ minHeight: "100vh" }}>
        <TopNav />
        <div
          className="layout__content"
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            height: "calc(100vh - 64px)",
          }}
        >
          <div className="realm-loader">
            <div className="realm-loader__orb" />
            <div className="realm-loader__text">
              Entering the Realm of Memories...
            </div>
          </div>
        </div>
      </main>
    );
  }

  // ── Main Render ──────────────────────────────────────────────────────
  return (
    <main className="layout realm-bg" style={{ minHeight: "100vh" }}>
      <TopNav />
      <div
        className="layout__content"
        style={{
          display: "flex",
          flexDirection: "column",
          height: "calc(100vh - 64px)",
          padding: 0,
          position: "relative",
        }}
      >
        {/* Title Overlay */}
        <div className="realm-title" style={{ zIndex: 10 }}>
          <h1>
            Realm of <span>Memories</span>
          </h1>
        </div>

        {/* 3D Graph Container (Wrapped for Layout) */}
        <div className="realm-graph-wrapper">
          <div ref={containerRef} className="realm-graph-container" />
          
          {/* HTML Overlay for Hover Effect */}
          <div ref={overlayRef} className="photo-bunch-overlay">
             {hoveredNode && (
               <div className="photo-bunch-name">
                  {hoveredNode.name || `Cluster ${hoveredNode.id}`}
               </div>
             )}
          </div>
        </div>

        {/* HUD Controls */}
        <div className="realm-hud">
          <button className="realm-hud__btn" onClick={zoomIn} title="Zoom In">
            +
          </button>
          <button className="realm-hud__btn" onClick={zoomOut} title="Zoom Out">
            −
          </button>
          <button className="realm-hud__btn" onClick={resetView} title="Reset View">
            ⌂
          </button>
          <div className="realm-hud__divider" />
          <div className="realm-hud__stat">
            <span>{graphData.nodes.length}</span> identities
          </div>
          <div className="realm-hud__stat">
            <span>{graphData.links.length}</span> connections
          </div>
        </div>

        {/* Sidebar — Memory Vault */}
        <div
          className={`realm-sidebar ${
            selectedNode ? "realm-sidebar--visible" : "realm-sidebar--hidden"
          }`}
        >
          {selectedNode && (
            <>
              <div className="realm-sidebar__hero">
                {selectedNode.cover_face_url && (
                  <div className="realm-sidebar__avatar">
                    <img
                      src={selectedNode.cover_face_url}
                      alt={selectedNode.name}
                    />
                  </div>
                )}
                <div className="realm-sidebar__info">
                  <h2 className="realm-sidebar__name">{selectedNode.name}</h2>
                  <div className="realm-sidebar__meta">
                    <span className="realm-sidebar__stat">
                      📸 {selectedNode.face_count} memories
                    </span>
                    {selectedNode.confirmed && (
                      <span
                        className="realm-sidebar__stat"
                        style={{
                          background: "rgba(255, 215, 0, 0.15)",
                          borderColor: "rgba(255, 215, 0, 0.25)",
                          color: "rgba(255, 215, 0, 0.9)",
                        }}
                      >
                        ✓ confirmed
                      </span>
                    )}
                  </div>
                </div>
                <button
                  className="realm-sidebar__close"
                  onClick={() => setSelectedNode(null)}
                >
                  ×
                </button>
              </div>

              <div className="realm-sidebar__grid">
                {loadingPhotos ? (
                  <div className="realm-sidebar__loading">
                    Loading memories...
                  </div>
                ) : (
                  sidebarPhotos.map((photo) => (
                    <div
                      key={photo.id}
                      className="realm-sidebar__photo"
                      onClick={() => setActivePhoto(photo)}
                    >
                      <img
                        src={getPhotoUrl(
                          photo.id,
                          photo.lib_hash || undefined
                        )}
                        alt="memory"
                        loading="lazy"
                      />
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Lightbox */}
      {activePhoto && (
        <div
          className="realm-lightbox"
          onClick={() => setActivePhoto(null)}
        >
          <button
            className="realm-lightbox__close"
            onClick={() => setActivePhoto(null)}
          >
            ×
          </button>
          <img
            src={getPhotoUrl(
              activePhoto.id,
              activePhoto.lib_hash || undefined
            )}
            alt="full memory"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </main>
  );
}

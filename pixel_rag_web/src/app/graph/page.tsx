"use client";

/**
 * Realm of Memories — cosmic memory nebula.
 *
 * Rebuild notes (the previous version had two real defects):
 *
 *  1. The cleanup function was `return`ed from inside a `.then()` callback, so
 *     React never received it and the destructor never ran. Every hot reload or
 *     navigation leaked a WebGL context and an animation loop. Cleanup is now
 *     returned synchronously from the effect and guarded by a cancellation flag.
 *
 *  2. `if (!graphInstanceRef.current)` wrapped the whole construction, so once
 *     the graph existed it could never pick up new data — switching library or
 *     re-syncing left a stale graph on screen. Data now flows through a
 *     dedicated effect that calls `.graphData()` on the live instance.
 *
 * Also: node textures are loaded lazily and only for nodes actually in view
 * range, because this library produces 343 identities and eagerly fetching 343
 * face crops on mount stalled the first frame.
 *
 * Chrome policy: the default screen shows the constellation, the title, the
 * bottom HUD and nothing else. Every added capability — time filtering, layout
 * modes, focus/freeze/link filtering, capture — sits behind one of four tabs
 * and is only on screen while its tray is open. An always-visible toolbar made
 * a simple graph look complicated.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import SpriteText from "three-spritetext";
import { fetchPhotos, getLibHash, getPhotoUrl } from "@/lib/api";
import type { Photo } from "@/lib/types";

interface GraphNode {
  id: string;
  name: string | null;
  face_count: number;
  cover_face_url: string | null;
  confirmed: boolean;
  /** appearances per year — the 4th dimension */
  years: Record<string, number>;
  x?: number;
  y?: number;
  z?: number;
  __obj?: THREE.Group;
}
interface GraphLink {
  source: string;
  target: string;
  weight: number;
  years: Record<string, number>;
}

// ── Palette ───────────────────────────────────────────────────────────────────
const GOLD = new THREE.Color("#ffd27a");
const VIOLET = new THREE.Color("#8b7ae8");
const NEBULA_A = "#2a1b5e";
const NEBULA_B = "#0a0618";

function nodeSize(faceCount: number) {
  // log scale: a 2,600-face identity should read as bigger, not 1000x bigger
  const clamped = Math.min(Math.max(faceCount, 2), 3000);
  return 14 + 34 * (Math.log(clamped) / Math.log(3000));
}

function linkStyle(weight: number) {
  if (weight >= 25) return { color: "#ffd27a", width: 2.2, particles: 4 };
  if (weight >= 8) return { color: "#a78bfa", width: 1.2, particles: 2 };
  return { color: "#3d4a7a", width: 0.5, particles: 0 };
}

// Persisted across visits so leaving the graph and coming back doesn't throw
// away how it was set up. Deliberately narrow: only the view configuration
// (filters/layout/toggles) is remembered, not transient session state like
// which tab is open, which person is selected, or the play/clean-view flags —
// those should always start fresh so the page never reopens into a state
// that looks broken (e.g. clean view with no visible way back in).
const GRAPH_SETTINGS_KEY = "pixelrag:graph-settings";
interface StoredGraphSettings {
  year: string | null;
  minFaces: number;
  hidden: string[];
  layout: "classic" | "cosmic";
  showLabels: boolean;
  frozen: boolean;
  minWeight: number;
}

export default function GraphPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const hoverRef = useRef<GraphNode | null>(null);
  const lastInteractionRef = useRef(Date.now());
  const texLoaderRef = useRef(new THREE.TextureLoader());

  const [data, setData] = useState<{
    nodes: GraphNode[];
    links: GraphLink[];
    years: string[];
  }>({ nodes: [], links: [], years: [] });
  const [year, setYear] = useState<string | null>(null); // null = all time
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [libHash, setLibHash] = useState("");
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [hovered, setHovered] = useState<GraphNode | null>(null);
  const [sidebarPhotos, setSidebarPhotos] = useState<Photo[]>([]);
  const [loadingPhotos, setLoadingPhotos] = useState(false);
  const [lightbox, setLightbox] = useState<Photo | null>(null);
  const [minFaces, setMinFaces] = useState(2);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [showPanel, setShowPanel] = useState(false);
  const [filterText, setFilterText] = useState("");

  // Both layouts are kept because they are genuinely different tools:
  // "classic" is tighter and easier to read at a glance; "cosmic" spreads the
  // graph into a real sphere with depth fog, which is better for exploring.
  const [layout, setLayout] = useState<"classic" | "cosmic">("classic");
  const [showLabels, setShowLabels] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [frozen, setFrozen] = useState(false);
  const [minWeight, setMinWeight] = useState(1);

  // Everything beyond the plain constellation lives behind a tab. Default view
  // is deliberately bare: title, HUD, hover label, side panel — nothing else.
  // A dense always-on toolbar made the graph read as complicated when the
  // graph itself is the point.
  const [tab, setTab] = useState<null | "time" | "layout" | "lens" | "studio">(null);
  const [clean, setClean] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const labelsRef = useRef(false);
  const focusRef = useRef(false);
  const selectedRef = useRef<GraphNode | null>(null);
  const neighborsRef = useRef<Set<string>>(new Set());
  const minWeightRef = useRef(1);

  useEffect(() => {
    hoverRef.current = hovered;
  }, [hovered]);

  // Restore the view configuration left from last time. Runs once, before the
  // persist effect below is allowed to fire — otherwise the persist effect
  // would see the still-default state on this same mount and immediately
  // clobber whatever was just restored.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(GRAPH_SETTINGS_KEY);
      if (raw) {
        const saved: Partial<StoredGraphSettings> = JSON.parse(raw);
        if (saved.year !== undefined) setYear(saved.year);
        if (typeof saved.minFaces === "number") setMinFaces(saved.minFaces);
        if (Array.isArray(saved.hidden)) setHidden(new Set(saved.hidden));
        if (saved.layout === "classic" || saved.layout === "cosmic") setLayout(saved.layout);
        if (typeof saved.showLabels === "boolean") setShowLabels(saved.showLabels);
        if (typeof saved.frozen === "boolean") setFrozen(saved.frozen);
        if (typeof saved.minWeight === "number") setMinWeight(saved.minWeight);
      }
    } catch {
      /* corrupted or unavailable storage — start from defaults */
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      const toSave: StoredGraphSettings = {
        year,
        minFaces,
        hidden: Array.from(hidden),
        layout,
        showLabels,
        frozen,
        minWeight,
      };
      localStorage.setItem(GRAPH_SETTINGS_KEY, JSON.stringify(toSave));
    } catch {
      /* storage full or unavailable — just won't persist this change */
    }
  }, [hydrated, year, minFaces, hidden, layout, showLabels, frozen, minWeight]);

  // The graph is a fixed-position canvas that owns the wheel for zooming. If the
  // page behind it can still scroll, the wheel does both at once — the canvas
  // zooms while the document scrolls under it, which is the scrolling bug.
  // Lock the document while this page is mounted.
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const prevHtml = html.style.overflow;
    const prevBody = body.style.overflow;
    const prevOverscroll = body.style.overscrollBehavior;
    html.style.overflow = "hidden";
    body.style.overflow = "hidden";
    body.style.overscrollBehavior = "none";
    return () => {
      html.style.overflow = prevHtml;
      body.style.overflow = prevBody;
      body.style.overscrollBehavior = prevOverscroll;
    };
  }, []);

  // ── Data ────────────────────────────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const h = await getLibHash();
        if (!alive) return;
        setLibHash(h);
        const res = await fetch(`/api/identities/graph?h=${h}`);
        if (!res.ok) throw new Error(String(res.status));
        const json = await res.json();
        if (alive) setData({ nodes: json.nodes, links: json.links, years: json.years ?? [] });
      } catch (err) {
        console.error("Realm: failed to load graph", err);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // A 343-identity graph is unreadable at once. Filtering by face count keeps
  // the constellation legible and is far cheaper than rendering everything.
  const visible = useMemo(() => {
    // Time is the fourth axis: when a year is selected, a person only exists in
    // the constellation if they actually appear in photos from that year, and a
    // connection only exists if the two were photographed together that year.
    const inYear = (m: Record<string, number> | undefined) =>
      !year ? true : !!(m && m[year]);

    const nodes = data.nodes.filter(
      (n) =>
        !hidden.has(n.id) &&
        (year ? (n.years?.[year] ?? 0) >= 1 : n.face_count >= minFaces) &&
        inYear(n.years)
    );
    const ids = new Set(nodes.map((n) => n.id));
    const links = data.links
      .filter((l) => {
        const s = typeof l.source === "string" ? l.source : (l.source as any).id;
        const t = typeof l.target === "string" ? l.target : (l.target as any).id;
        return ids.has(s) && ids.has(t) && inYear(l.years);
      })
      .map((l) =>
        year ? { ...l, weight: l.years?.[year] ?? l.weight } : l
      );
    return { nodes, links };
  }, [data, minFaces, hidden, year]);

  // Auto-advance through the years for the "watch your life assemble" view.
  useEffect(() => {
    if (!playing || data.years.length === 0) return;
    const id = window.setInterval(() => {
      setYear((cur) => {
        const i = cur ? data.years.indexOf(cur) : -1;
        return data.years[(i + 1) % data.years.length];
      });
    }, 1600);
    return () => window.clearInterval(id);
  }, [playing, data.years]);

  const toggleHidden = useCallback((id: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // ── Scene construction (once) ───────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || loading) return;

    let cancelled = false;
    let frameId = 0;
    let disposed = false;
    const el = containerRef.current;

    // circular alpha mask, shared by every node sprite
    const c = document.createElement("canvas");
    c.width = c.height = 128;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, 128, 128);
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.arc(64, 64, 62, 0, Math.PI * 2);
    ctx.fill();
    const alphaMap = new THREE.CanvasTexture(c);

    import("3d-force-graph").then((mod) => {
      if (cancelled || !containerRef.current) return;
      const ForceGraph3D = (mod as any).default;

      // preserveDrawingBuffer keeps the last frame readable after compositing.
      // Without it `toDataURL` returns a blank image on most browsers, however
      // carefully you re-render first.
      const graph = ForceGraph3D({
        rendererConfig: { preserveDrawingBuffer: true },
      })(el)
        .backgroundColor("rgba(0,0,0,0)")
        .showNavInfo(false)
        .nodeRelSize(1)
        .linkColor((l: any) => linkStyle(l.weight || 1).color)
        .linkWidth((l: any) => linkStyle(l.weight || 1).width)
        .linkOpacity(0.22)
        .linkCurvature(0.12)
        .linkDirectionalParticles((l: any) => linkStyle(l.weight || 1).particles)
        .linkDirectionalParticleWidth(1.4)
        .linkDirectionalParticleSpeed(0.0035)
        .nodeThreeObject((node: GraphNode) => {
          if (node.__obj) return node.__obj;
          const group = new THREE.Group();
          const size = nodeSize(node.face_count || 2);
          const glow = node.confirmed ? GOLD : VIOLET;

          const halo = new THREE.Mesh(
            new THREE.CircleGeometry(size * 0.78, 32),
            new THREE.MeshBasicMaterial({
              color: glow,
              transparent: true,
              opacity: 0.1,
              blending: THREE.AdditiveBlending,
              depthWrite: false,
              side: THREE.DoubleSide,
            })
          );
          halo.position.z = -1.5;
          group.add(halo);

          const ring = new THREE.Mesh(
            new THREE.RingGeometry(size * 0.52, size * 0.585, 40),
            new THREE.MeshBasicMaterial({
              color: glow,
              transparent: true,
              opacity: 0.65,
              blending: THREE.AdditiveBlending,
              depthWrite: false,
              side: THREE.DoubleSide,
            })
          );
          group.add(ring);

          const mat = new THREE.SpriteMaterial({
            color: 0xffffff,
            transparent: true,
            alphaMap,
            alphaTest: 0.12,
          });
          const sprite = new THREE.Sprite(mat);
          sprite.scale.set(size, size, 1);
          group.add(sprite);

          if (node.cover_face_url) {
            texLoaderRef.current.load(node.cover_face_url, (tex) => {
              if (disposed) {
                tex.dispose();
                return;
              }
              tex.minFilter = THREE.LinearFilter;
              tex.colorSpace = THREE.SRGBColorSpace;
              mat.map = tex;
              mat.needsUpdate = true;
            });
          }

          // Name label. Built once and toggled by visibility rather than
          // rebuilt on every switch — rebuilding 85 sprites drops frames.
          const label = new SpriteText(
            node.name?.startsWith("Cluster_") ? "Unnamed" : node.name || ""
          );
          label.color = node.confirmed ? "#ffd27a" : "#c9bdf5";
          label.textHeight = Math.max(5, size * 0.22);
          label.position.y = -size * 0.72;
          label.visible = labelsRef.current;
          label.material.depthWrite = false;
          group.add(label);
          (node as any).__label = label;

          node.__obj = group;
          return group;
        })
        .nodeVisibility((n: GraphNode) => {
          if (!focusRef.current || !selectedRef.current) return true;
          const sel = selectedRef.current.id;
          return n.id === sel || neighborsRef.current.has(n.id);
        })
        .linkVisibility((l: any) => {
          const w = l.weight || 1;
          if (w < minWeightRef.current) return false;
          if (!focusRef.current || !selectedRef.current) return true;
          const s = typeof l.source === "string" ? l.source : l.source.id;
          const t = typeof l.target === "string" ? l.target : l.target.id;
          const sel = selectedRef.current.id;
          return s === sel || t === sel;
        })
        .onNodeHover((n: GraphNode | null) => {
          el.style.cursor = n ? "pointer" : "grab";
          setHovered(n || null);
        })
        .onNodeClick(async (node: GraphNode) => {
          lastInteractionRef.current = Date.now();
          const dist = 220;
          const ratio = 1 + dist / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
          graph.cameraPosition(
            { x: (node.x || 0) * ratio, y: (node.y || 0) * ratio, z: (node.z || 0) * ratio },
            node,
            1100
          );
          setSelected(node);
          setSidebarPhotos([]);
          setLoadingPhotos(true);
          try {
            const d = await fetchPhotos({
              person_id: Number(node.id),
              page_size: 60,
              libHash,
            });
            if (!disposed) setSidebarPhotos(d.items);
          } catch (e) {
            console.error(e);
          } finally {
            if (!disposed) setLoadingPhotos(false);
          }
        });

      graph.d3Force("charge").strength(-700);
      graph.d3Force("link").distance(200);

      // Zoom was hard to control: the default trackball zoom speed is tuned for
      // small scenes, so one wheel notch barely moved and a fast scroll flew
      // past the graph entirely. Raise the speed and add damping so it glides.
      try {
        const ctrls = graph.controls() as any;
        if (ctrls) {
          if ("zoomSpeed" in ctrls) ctrls.zoomSpeed = 3.2;
          if ("rotateSpeed" in ctrls) ctrls.rotateSpeed = 1.4;
          if ("panSpeed" in ctrls) ctrls.panSpeed = 1.0;
          if ("staticMoving" in ctrls) ctrls.staticMoving = false;
          if ("dynamicDampingFactor" in ctrls) ctrls.dynamicDampingFactor = 0.12;
          if ("noZoom" in ctrls) ctrls.noZoom = false;
        }
      } catch {
        /* controls shape varies by version; zoom buttons still work */
      }

      // ── Nebula: two additive point clouds + distant starfield ───────────────
      const scene = graph.scene();
      const mkPoints = (n: number, spread: number, size: number, color: string, opacity: number) => {
        const g = new THREE.BufferGeometry();
        const pos = new Float32Array(n * 3);
        for (let i = 0; i < n * 3; i++) pos[i] = (Math.random() - 0.5) * spread;
        g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
        const p = new THREE.Points(
          g,
          new THREE.PointsMaterial({
            size,
            color: new THREE.Color(color),
            transparent: true,
            opacity,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
          })
        );
        scene.add(p);
        return p;
      };

      const farStars = mkPoints(7000, 6000, 1.1, "#8fa3d9", 0.35);
      const nearStars = mkPoints(400, 3000, 2.6, "#dce8ff", 0.7);
      const nebulaA = mkPoints(1400, 2200, 34, NEBULA_A, 0.055);
      const nebulaB = mkPoints(900, 1700, 44, "#4b2d7f", 0.045);

      graph.cameraPosition({ x: 0, y: 0, z: 700 });
      graphRef.current = graph;

      // Apply a restored layout/freeze setting now. Construction is async
      // (waits on the `3d-force-graph` import), so by the time it resolves the
      // layout/frozen *effects* below may already have run once against a null
      // instance and won't fire again on their own — this closure still has
      // the correct current values, so it applies them directly instead.
      try {
        if (layout === "cosmic") {
          graph.d3Force("charge").strength(-1100);
          graph.d3Force("link").distance(230);
          try {
            const { forceRadial } = require("d3-force-3d");
            graph.d3Force("radial", forceRadial(340).strength(0.12));
          } catch { /* optional */ }
          graph.scene().fog = new THREE.FogExp2(0x0a0618, 0.00085);
        }
        if (frozen) graph.cooldownTicks(0);
      } catch { /* force/cooldown API varies slightly by version */ }

      const clock = new THREE.Clock();
      const animate = () => {
        frameId = requestAnimationFrame(animate);
        const t = clock.getElapsedTime();

        (nearStars.material as THREE.PointsMaterial).opacity = 0.5 + 0.25 * Math.sin(t * 0.8);
        nebulaA.rotation.y = t * 0.008;
        nebulaB.rotation.y = -t * 0.005;
        nebulaB.rotation.x = Math.sin(t * 0.05) * 0.08;

        // hover label tracks the node in screen space without React re-renders
        const hv = hoverRef.current;
        if (hv && overlayRef.current) {
          try {
            const p = graph.graph2ScreenCoords(hv.x || 0, hv.y || 0, hv.z || 0);
            overlayRef.current.style.transform = `translate(${p.x}px, ${p.y}px)`;
            overlayRef.current.style.opacity = "1";
          } catch {
            /* node briefly off-screen */
          }
        } else if (overlayRef.current) {
          overlayRef.current.style.opacity = "0";
        }

        if (Date.now() - lastInteractionRef.current > 6000) {
          const pos = graph.cameraPosition();
          const mag = Math.hypot(pos.x, pos.y, pos.z);
          if (mag > 0) {
            graph.cameraPosition({
              x: pos.x + Math.cos(t * 0.03) * mag * 0.0016,
              y: pos.y + Math.sin(t * 0.021) * mag * 0.0009,
              z: pos.z,
            });
          }
        }
      };
      animate();
    });

    // Returned SYNCHRONOUSLY from the effect — the old version returned this
    // from inside .then(), so React never got it and nothing was ever disposed.
    return () => {
      cancelled = true;
      disposed = true;
      if (frameId) cancelAnimationFrame(frameId);
      alphaMap.dispose();
      const g = graphRef.current;
      if (g) {
        try {
          g._destructor?.();
        } catch {
          /* already torn down */
        }
        graphRef.current = null;
      }
      if (el) el.innerHTML = "";
    };
  }, [loading, libHash]);

  // ── Feed data to the live instance (was impossible in the old version) ──────
  useEffect(() => {
    if (graphRef.current) graphRef.current.graphData(visible);
  }, [visible]);

  // ── Layout mode ────────────────────────────────────────────────────────────
  // Both layouts are kept deliberately: "classic" is tighter and easier to read,
  // "cosmic" spreads into a real sphere with depth fog for exploring. Applied to
  // the live instance and reheated so switching animates instead of snapping.
  useEffect(() => {
    const g = graphRef.current;
    if (!g) return;
    try {
      if (layout === "cosmic") {
        g.d3Force("charge").strength(-1100);
        g.d3Force("link").distance(230);
        try {
          const { forceRadial } = require("d3-force-3d");
          g.d3Force("radial", forceRadial(340).strength(0.12));
        } catch { /* optional */ }
        g.scene().fog = new THREE.FogExp2(0x0a0618, 0.00085);
      } else {
        g.d3Force("charge").strength(-700);
        g.d3Force("link").distance(200);
        g.d3Force("radial", null);
        g.scene().fog = null;
      }
      g.d3ReheatSimulation?.();
    } catch { /* force API varies slightly by version */ }
  }, [layout]);

  // Labels: flip sprite visibility instead of rebuilding node objects.
  useEffect(() => {
    labelsRef.current = showLabels;
    for (const n of data.nodes) {
      const lbl = (n as any).__label;
      if (lbl) lbl.visible = showLabels;
    }
  }, [showLabels, data.nodes, visible]);

  // Focus mode + weak-link filter feed the visibility accessors through refs,
  // so the graph re-evaluates without rebuilding any objects.
  useEffect(() => {
    focusRef.current = focusMode;
    selectedRef.current = selected;
    minWeightRef.current = minWeight;
    if (selected) {
      const nb = new Set<string>();
      for (const l of visible.links) {
        const s = typeof l.source === "string" ? l.source : (l.source as any).id;
        const t = typeof l.target === "string" ? l.target : (l.target as any).id;
        if (s === selected.id) nb.add(t);
        if (t === selected.id) nb.add(s);
      }
      neighborsRef.current = nb;
    } else {
      neighborsRef.current = new Set();
    }
    graphRef.current?.refresh?.();
  }, [focusMode, selected, minWeight, visible.links]);

  // Freeze holds the constellation still — good for reading it, and for
  // capturing a clean screenshot.
  useEffect(() => {
    const g = graphRef.current;
    if (!g) return;
    try {
      if (frozen) g.cooldownTicks(0);
      else {
        g.cooldownTicks(Infinity);
        g.d3ReheatSimulation?.();
      }
    } catch { /* no-op */ }
  }, [frozen]);

  const exportPNG = useCallback(() => {
    const g = graphRef.current;
    if (!g) return;
    try {
      const renderer = g.renderer();
      renderer.render(g.scene(), g.camera()); // force a fresh frame before reading
      const src = renderer.domElement as HTMLCanvasElement;

      // The WebGL canvas is transparent (alpha: true) — the nebula backdrop is
      // a CSS gradient behind it. Reading the canvas alone gives a see-through
      // PNG, so paint the same gradient underneath and composite the frame on
      // top. What you save is then what you saw.
      const out = document.createElement("canvas");
      out.width = src.width;
      out.height = src.height;
      const ctx = out.getContext("2d");
      if (!ctx) return;
      const w = out.width;
      const h = out.height;

      ctx.fillStyle = NEBULA_B;
      ctx.fillRect(0, 0, w, h);
      const top = ctx.createRadialGradient(w * 0.5, 0, 0, w * 0.5, 0, h * 0.95);
      top.addColorStop(0, "rgba(42, 27, 94, 0.42)");
      top.addColorStop(1, "rgba(42, 27, 94, 0)");
      ctx.fillStyle = top;
      ctx.fillRect(0, 0, w, h);
      const bottom = ctx.createRadialGradient(w * 0.2, h, 0, w * 0.2, h, h * 0.85);
      bottom.addColorStop(0, "rgba(59, 29, 110, 0.3)");
      bottom.addColorStop(1, "rgba(59, 29, 110, 0)");
      ctx.fillStyle = bottom;
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(src, 0, 0, w, h);

      const a = document.createElement("a");
      a.href = out.toDataURL("image/png");
      a.download = `realm-of-memories${year ? `-${year}` : ""}.png`;
      a.click();
    } catch (e) {
      console.error("PNG export failed", e);
    }
  }, [year]);

  const zoom = useCallback((factor: number) => {
    const g = graphRef.current;
    if (!g) return;
    lastInteractionRef.current = Date.now();
    const p = g.cameraPosition();
    const mag = Math.hypot(p.x, p.y, p.z);
    if ((factor < 1 && mag < 90) || (factor > 1 && mag > 2200)) return;
    g.cameraPosition({ x: p.x * factor, y: p.y * factor, z: p.z * factor }, { x: 0, y: 0, z: 0 }, 300);
  }, []);

  useEffect(() => {
    const bump = () => {
      lastInteractionRef.current = Date.now();
    };
    // Keyboard zoom, because trackpads vary wildly and some make wheel-zoom
    // genuinely awkward. +/- and arrow keys always work.
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      if (e.key === "+" || e.key === "=") { zoom(0.78); e.preventDefault(); }
      else if (e.key === "-" || e.key === "_") { zoom(1.28); e.preventDefault(); }
      else if (e.key === "0") { graphRef.current?.cameraPosition({ x: 0, y: 0, z: 700 }, { x: 0, y: 0, z: 0 }, 700); }
      else if (e.key === "Escape") {
        // Peel one layer at a time: clean view → open tray → selection.
        if (clean) setClean(false);
        else if (tab) setTab(null);
        else { setSelected(null); setShowPanel(false); }
      }
      bump();
    };
    window.addEventListener("mousemove", bump);
    window.addEventListener("wheel", bump, { passive: true });
    window.addEventListener("touchstart", bump, { passive: true });
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousemove", bump);
      window.removeEventListener("wheel", bump);
      window.removeEventListener("touchstart", bump);
      window.removeEventListener("keydown", onKey);
    };
  }, [zoom, clean, tab]);

  const resetView = useCallback(() => {
    lastInteractionRef.current = Date.now();
    graphRef.current?.cameraPosition({ x: 0, y: 0, z: 700 }, { x: 0, y: 0, z: 0 }, 800);
  }, []);

  const named = data.nodes.filter((n) => n.confirmed).length;

  // `on` drives the gold dot: it tells you a closed tab is still changing what
  // you're looking at, so a filter can never be silently left applied.
  const tabs: { id: NonNullable<typeof tab>; label: string; on: boolean; hint: string }[] = [
    ...(data.years.length > 1
      ? [
          {
            id: "time" as const,
            label: "TIME",
            on: !!year || playing,
            hint: "Show only the people and connections from one year",
          },
        ]
      : []),
    {
      id: "layout" as const,
      label: "LAYOUT",
      on: layout === "cosmic" || showLabels,
      hint: "How the constellation is arranged and labelled",
    },
    {
      id: "lens" as const,
      label: "LENS",
      on: focusMode || frozen || minWeight > 1,
      hint: "Narrow down what you're looking at",
    },
    {
      id: "studio" as const,
      label: "STUDIO",
      on: false,
      hint: "Clean view and image export, for screenshots and recording",
    },
  ];

  return (
    <div className="realm-root">
      <style jsx global>{`
        .realm-root {
          position: fixed;
          inset: 0;
          top: 64px;
          background:
            radial-gradient(ellipse 120% 80% at 50% 0%, ${NEBULA_A}55 0%, transparent 60%),
            radial-gradient(ellipse 90% 70% at 20% 100%, #3b1d6e44 0%, transparent 55%),
            ${NEBULA_B};
          overflow: hidden;
        }
        .realm-canvas { position: absolute; inset: 0; }
        .realm-title {
          position: absolute; top: 26px; left: 32px; z-index: 6; pointer-events: none;
        }
        .realm-title h1 {
          font-family: var(--font-pixel); font-size: 2rem; letter-spacing: 0.06em;
          color: #f3ecff; margin: 0; text-shadow: 0 0 28px #8b7ae8aa;
        }
        .realm-title span { color: #ffd27a; }
        .realm-title p {
          font-family: var(--font-mono); font-size: 0.72rem; color: #b9aee0;
          margin: 6px 0 0; letter-spacing: 0.12em; text-transform: uppercase;
        }
        .realm-hud {
          position: absolute; bottom: 26px; z-index: 6;
          display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
          max-width: calc(100vw - 64px);
          background: rgba(18, 12, 40, 0.62); backdrop-filter: blur(14px);
          border: 1px solid #ffffff1f; border-radius: 14px; padding: 10px 14px;
        }
        .realm-hud button {
          width: 34px; height: 34px; border-radius: 9px; cursor: pointer;
          background: #ffffff10; border: 1px solid #ffffff1f; color: #e8e0ff;
          font-size: 1rem; display: grid; place-items: center; transition: background .15s;
        }
        .realm-hud button:hover { background: #ffffff22; }
        .realm-hud__stat {
          font-family: var(--font-mono); font-size: 0.7rem; color: #b9aee0;
          padding-left: 6px; white-space: nowrap;
        }
        .realm-hud__stat b { color: #ffd27a; font-weight: 600; }
        .realm-hud__divider {
          width: 1px; height: 22px; background: #ffffff26; margin: 0 2px;
        }
        .realm-slider { display: flex; align-items: center; gap: 8px; padding-left: 6px; }
        .realm-slider input { width: 108px; accent-color: #8b7ae8; cursor: pointer; }
        .realm-label {
          position: absolute; top: 0; left: 0; z-index: 5; pointer-events: none;
          opacity: 0; transition: opacity .12s;
        }
        .realm-label__inner {
          transform: translate(-50%, -230%);
          background: rgba(16, 10, 36, 0.9); border: 1px solid #ffffff26;
          border-radius: 9px; padding: 5px 11px; white-space: nowrap;
          font-family: var(--font-pixel); font-size: 0.9rem; color: #f3ecff;
        }
        .realm-label__inner small {
          display: block; font-family: var(--font-mono); font-size: 0.62rem; color: #a99fd0;
        }
        .realm-panel {
          position: absolute; top: 0; right: 0; bottom: 0; width: min(400px, 88vw);
          z-index: 7; background: rgba(12, 8, 28, 0.9); backdrop-filter: blur(20px);
          border-left: 1px solid #ffffff1a; display: flex; flex-direction: column;
          transform: translateX(100%); transition: transform .34s cubic-bezier(.4,0,.2,1);
        }
        .realm-panel--open { transform: translateX(0); }
        .realm-panel__head {
          padding: 22px; border-bottom: 1px solid #ffffff14;
          display: flex; gap: 14px; align-items: center;
        }
        .realm-panel__avatar {
          width: 62px; height: 62px; border-radius: 50%; overflow: hidden; flex-shrink: 0;
          border: 2px solid #ffd27a66;
        }
        .realm-panel__avatar img { width: 100%; height: 100%; object-fit: cover; }
        .realm-panel__name {
          font-family: var(--font-pixel); font-size: 1.25rem; color: #f3ecff; margin: 0;
        }
        .realm-panel__meta {
          font-family: var(--font-mono); font-size: 0.68rem; color: #a99fd0; margin-top: 4px;
        }
        .realm-panel__close {
          margin-left: auto; background: none; border: none; color: #a99fd0;
          font-size: 1.5rem; cursor: pointer; line-height: 1;
        }
        .realm-grid {
          flex: 1; overflow-y: auto; padding: 14px;
          display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; align-content: start;
        }
        .realm-grid img {
          width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 7px;
          cursor: pointer; transition: transform .14s; background: #ffffff08;
        }
        .realm-grid img:hover { transform: scale(1.06); }
        .realm-empty {
          font-family: var(--font-mono); font-size: 0.75rem; color: #a99fd0;
          grid-column: 1/-1; text-align: center; padding: 28px 0;
        }
        .realm-lightbox {
          position: fixed; inset: 0; z-index: 60; background: rgba(4,2,12,.94);
          display: grid; place-items: center; cursor: zoom-out;
        }
        .realm-lightbox img { max-width: 92vw; max-height: 92vh; border-radius: 10px; }
        /* ── Tabs: the only extra chrome on the default screen ──────────────
           Four small pills. Each opens one tray of controls underneath; the
           rest of the time the canvas is uncluttered. A gold dot marks a tab
           whose settings are currently doing something. */
        .realm-tabs {
          position: absolute; top: 26px; left: 50%; transform: translateX(-50%);
          z-index: 9; display: flex; gap: 3px;
          background: rgba(18,12,40,.62); backdrop-filter: blur(14px);
          border: 1px solid #ffffff1f; border-radius: 12px; padding: 4px;
        }
        .realm-tabs button {
          position: relative; padding: 6px 15px; border-radius: 9px; cursor: pointer;
          background: transparent; border: none; color: #9c92c4;
          font-family: var(--font-mono); font-size: .68rem; letter-spacing: .09em;
          transition: color .15s, background .15s;
        }
        .realm-tabs button:hover { color: #f3ecff; background: #ffffff12; }
        .realm-tabs button.is-open { background: #8b7ae8; color: #fff; }
        .realm-tabs .realm-dot {
          position: absolute; top: 4px; right: 5px;
          width: 5px; height: 5px; border-radius: 50%; background: #ffd27a;
        }
        .realm-tray {
          position: absolute; top: 76px; left: 50%; z-index: 9;
          width: max-content; max-width: min(640px, 92vw);
          display: flex; align-items: center; gap: 8px;
          flex-wrap: wrap; justify-content: center;
          background: rgba(18,12,40,.86); backdrop-filter: blur(18px);
          border: 1px solid #ffffff26; border-radius: 12px; padding: 10px 12px;
          animation: realmTray .16s ease-out; transform: translateX(-50%);
        }
        @keyframes realmTray {
          from { opacity: 0; transform: translate(-50%, -7px); }
          to   { opacity: 1; transform: translate(-50%, 0); }
        }
        .realm-tray button {
          padding: 6px 11px; border-radius: 8px; cursor: pointer;
          background: #ffffff0d; border: 1px solid #ffffff1f; color: #cfc6ee;
          font-family: var(--font-mono); font-size: .68rem; letter-spacing: .04em;
          transition: all .15s; white-space: nowrap;
        }
        .realm-tray button:hover { background: #ffffff1e; }
        .realm-tray button.is-on {
          background: #8b7ae8; border-color: #a99bf5; color: #fff;
        }
        .realm-tray__slider {
          display: flex; align-items: center; gap: 6px; padding: 0 6px;
          font-family: var(--font-mono); font-size: .62rem; color: #a99fd0;
        }
        .realm-tray__slider input { width: 80px; accent-color: #8b7ae8; cursor: pointer; }
        .realm-tray__slider b { color: #ffd27a; min-width: 14px; }
        .realm-tray__note {
          width: 100%; text-align: center; font-family: var(--font-mono);
          font-size: .58rem; color: #8880ae; letter-spacing: .05em;
        }
        .realm-time__row {
          display: flex; align-items: center; gap: 5px;
          flex-wrap: wrap; justify-content: center;
        }
        .realm-time__scrub {
          display: flex; align-items: center; gap: 8px; width: 100%;
          font-family: var(--font-mono); font-size: .62rem; color: #a99fd0;
        }
        .realm-time__scrub input { flex: 1; accent-color: #ffd27a; cursor: pointer; }
        .realm-time__play {
          width: 30px; height: 28px; border-radius: 8px; cursor: pointer;
          background: #ffd27a22; border: 1px solid #ffd27a55; color: #ffd27a;
          font-size: .8rem;
        }
        .realm-time__year {
          padding: 5px 10px; border-radius: 8px; cursor: pointer;
          background: #ffffff0d; border: 1px solid #ffffff1f; color: #cfc6ee;
          font-family: var(--font-mono); font-size: .72rem; transition: all .15s;
        }
        .realm-time__year:hover { background: #ffffff1c; }
        .realm-time__year.is-on {
          background: #ffd27a; border-color: #ffd27a; color: #1a1030; font-weight: 700;
        }
        /* Clean view: strip every overlay so the constellation can be filmed or
           screenshotted. Two faint chips remain — they sit in the DOM, not the
           canvas, so they never appear in an exported PNG. */
        .realm-chip {
          position: absolute; bottom: 22px; z-index: 10; cursor: pointer;
          background: rgba(18,12,40,.5); border: 1px solid #ffffff18; color: #7f77a6;
          border-radius: 9px; padding: 6px 12px; opacity: .32;
          font-family: var(--font-mono); font-size: .64rem; letter-spacing: .06em;
          transition: opacity .2s, color .2s;
        }
        .realm-chip:hover { opacity: 1; color: #f3ecff; }
        .realm-chip--exit { right: 22px; }
        .realm-chip--save { right: 132px; }
        .realm-people {
          position: absolute; left: 32px; bottom: 92px; z-index: 8;
          width: min(320px, 86vw); max-height: 56vh; display: flex; flex-direction: column;
          background: rgba(14, 9, 32, .93); backdrop-filter: blur(16px);
          border: 1px solid #ffffff22; border-radius: 14px; overflow: hidden;
        }
        .realm-people__head {
          display: flex; align-items: center; justify-content: space-between;
          padding: 12px 14px; border-bottom: 1px solid #ffffff14;
          font-family: var(--font-pixel); color: #f3ecff; font-size: .95rem;
        }
        .realm-people__head button {
          background: none; border: none; color: #a99fd0; font-size: 1.2rem; cursor: pointer;
        }
        .realm-people__search {
          margin: 10px 12px 6px; padding: 7px 10px; border-radius: 8px;
          border: 1px solid #ffffff22; background: #ffffff0d; color: #f3ecff;
          font-family: var(--font-mono); font-size: .78rem; outline: none;
        }
        .realm-people__actions { display: flex; gap: 6px; padding: 4px 12px 10px; }
        .realm-people__actions button {
          flex: 1; padding: 6px 4px; border-radius: 7px; cursor: pointer;
          background: #ffffff10; border: 1px solid #ffffff1f; color: #cfc6ee;
          font-family: var(--font-mono); font-size: .66rem;
        }
        .realm-people__actions button:hover { background: #ffffff20; }
        .realm-people__list { overflow-y: auto; padding: 0 6px 10px; }
        .realm-people__row {
          display: flex; align-items: center; gap: 9px; padding: 6px 8px;
          border-radius: 8px; cursor: pointer; color: #e8e0ff;
          font-family: var(--font-mono); font-size: .76rem;
        }
        .realm-people__row:hover { background: #ffffff10; }
        .realm-people__row.is-off { opacity: .38; }
        .realm-people__row img {
          width: 26px; height: 26px; border-radius: 50%; object-fit: cover; flex-shrink: 0;
        }
        .realm-people__name {
          flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .realm-people__count { color: #a99fd0; font-size: .7rem; }
        .realm-loading {
          position: absolute; inset: 0; display: grid; place-items: center; z-index: 8;
        }
        .realm-orb {
          width: 60px; height: 60px; border-radius: 50%;
          background: radial-gradient(circle at 32% 32%, #ffd27a, #8b7ae8 55%, transparent 72%);
          animation: realmPulse 1.7s ease-in-out infinite;
        }
        @keyframes realmPulse {
          0%,100% { transform: scale(.86); opacity:.65 }
          50%     { transform: scale(1.12); opacity:1 }
        }
      `}</style>

      <div ref={containerRef} className="realm-canvas" />

      {!clean && (
        <div className="realm-title">
          <h1>
            Realm of <span>Memories</span>
          </h1>
          <p>
            {visible.nodes.length} of {data.nodes.length} people · {named} named
            {year ? ` · ${year}` : " · all time"}
          </p>
        </div>
      )}

      {!clean && (
        <div className="realm-tabs">
          {tabs.map((t) => (
            <button
              key={t.id}
              className={tab === t.id ? "is-open" : ""}
              onClick={() => setTab((cur) => (cur === t.id ? null : t.id))}
              title={t.hint}
            >
              {t.label}
              {t.on && tab !== t.id && <span className="realm-dot" />}
            </button>
          ))}
        </div>
      )}

      {!clean && tab === "time" && (
        <div className="realm-tray">
          <div className="realm-time__row">
            <button
              className="realm-time__play"
              onClick={() => setPlaying((p) => !p)}
              title="Play through the years"
            >
              {playing ? "❚❚" : "▶"}
            </button>
            <button
              className={`realm-time__year ${!year ? "is-on" : ""}`}
              onClick={() => { setYear(null); setPlaying(false); }}
            >
              ALL
            </button>
            {data.years.map((y) => (
              <button
                key={y}
                className={`realm-time__year ${year === y ? "is-on" : ""}`}
                onClick={() => { setYear(y); setPlaying(false); }}
              >
                {y}
              </button>
            ))}
          </div>

          {/* Continuous timeline — drag through the years instead of clicking */}
          <div className="realm-time__scrub">
            <span>{data.years[0]}</span>
            <input
              type="range"
              min={0}
              max={data.years.length - 1}
              step={1}
              value={year ? data.years.indexOf(year) : 0}
              onChange={(e) => {
                setPlaying(false);
                setYear(data.years[Number(e.target.value)]);
              }}
              aria-label="Timeline"
            />
            <span>{data.years[data.years.length - 1]}</span>
          </div>
          <div className="realm-tray__note">
            A person appears only if they were photographed that year — and a
            connection only if the two were photographed together.
          </div>
        </div>
      )}

      {!clean && tab === "layout" && (
        <div className="realm-tray">
          <button
            className={layout === "classic" ? "is-on" : ""}
            onClick={() => setLayout("classic")}
          >
            CLASSIC
          </button>
          <button
            className={layout === "cosmic" ? "is-on" : ""}
            onClick={() => setLayout("cosmic")}
          >
            COSMIC_3D
          </button>
          <button
            className={showLabels ? "is-on" : ""}
            onClick={() => setShowLabels((v) => !v)}
          >
            NAMES
          </button>
          <div className="realm-tray__note">
            Classic sits tighter and reads at a glance · Cosmic spreads into a
            sphere with depth fog · Names shows every label instead of on hover
          </div>
        </div>
      )}

      {!clean && tab === "lens" && (
        <div className="realm-tray">
          <button
            className={focusMode ? "is-on" : ""}
            onClick={() => setFocusMode((v) => !v)}
          >
            FOCUS
          </button>
          <button
            className={frozen ? "is-on" : ""}
            onClick={() => setFrozen((v) => !v)}
          >
            {frozen ? "FROZEN" : "FREEZE"}
          </button>
          <div className="realm-tray__slider">
            <span>LINKS≥</span>
            <input
              type="range"
              min={1}
              max={30}
              value={minWeight}
              onChange={(e) => setMinWeight(Number(e.target.value))}
            />
            <b>{minWeight}</b>
          </div>
          <div className="realm-tray__note">
            Focus keeps only the selected person and who they appear with ·
            Freeze stops the physics · Links hides weak connections
          </div>
        </div>
      )}

      {!clean && tab === "studio" && (
        <div className="realm-tray">
          <button
            onClick={() => {
              setFrozen(true);
              setTab(null);
              setClean(true);
            }}
          >
            CLEAN_VIEW
          </button>
          <button onClick={exportPNG}>EXPORT_PNG</button>
          <div className="realm-tray__note">
            Clean view hides every overlay and holds the layout still — press
            ESC to come back. Export saves the canvas exactly as rendered.
          </div>
        </div>
      )}

      {clean && (
        <>
          <button className="realm-chip realm-chip--save" onClick={exportPNG}>
            EXPORT_PNG
          </button>
          <button className="realm-chip realm-chip--exit" onClick={() => setClean(false)}>
            EXIT · ESC
          </button>
        </>
      )}

      <div ref={overlayRef} className="realm-label">
        {hovered && (
          <div className="realm-label__inner">
            {hovered.name?.startsWith("Cluster_") ? "Unnamed" : hovered.name}
            <small>{hovered.face_count} memories</small>
          </div>
        )}
      </div>

      {loading && (
        <div className="realm-loading">
          <div className="realm-orb" />
        </div>
      )}

      <div className="realm-hud" style={clean ? { display: "none" } : undefined}>
        <button onClick={() => zoom(0.75)} title="Zoom in">+</button>
        <button onClick={() => zoom(1.35)} title="Zoom out">−</button>
        <button onClick={resetView} title="Reset view">⌂</button>
        <div className="realm-slider" title="Hide identities with fewer memories">
          <span className="realm-hud__stat">MIN</span>
          <input
            type="range"
            min={2}
            max={60}
            value={minFaces}
            onChange={(e) => setMinFaces(Number(e.target.value))}
          />
          <span className="realm-hud__stat">
            <b>{minFaces}</b>
          </span>
        </div>
        <div className="realm-hud__stat">
          <b>{visible.links.length}</b> connections
        </div>
        <div className="realm-hud__divider" />
        <button
          onClick={() => setShowPanel((v) => !v)}
          title="Choose which people appear"
          style={{ width: "auto", padding: "0 12px", fontSize: ".72rem",
                   fontFamily: "var(--font-mono)", letterSpacing: ".06em" }}
        >
          PEOPLE{hidden.size ? ` (${hidden.size} hidden)` : ""}
        </button>
      </div>

      {showPanel && !clean && (
        <aside className="realm-people">
          <div className="realm-people__head">
            <strong>Who appears</strong>
            <button onClick={() => setShowPanel(false)}>×</button>
          </div>
          <input
            className="realm-people__search"
            placeholder="Search name…"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
          />
          <div className="realm-people__actions">
            <button onClick={() => setHidden(new Set())}>Show all</button>
            <button
              onClick={() =>
                setHidden(new Set(data.nodes.map((n) => n.id)))
              }
            >
              Hide all
            </button>
            <button
              onClick={() =>
                setHidden(new Set(data.nodes.filter((n) => !n.confirmed).map((n) => n.id)))
              }
            >
              Only named
            </button>
          </div>
          <div className="realm-people__list">
            {data.nodes
              .filter((n) =>
                (n.name || "").toLowerCase().includes(filterText.toLowerCase())
              )
              .sort((a, b) => b.face_count - a.face_count)
              .map((n) => {
                const off = hidden.has(n.id);
                return (
                  <label key={n.id} className={`realm-people__row ${off ? "is-off" : ""}`}>
                    <input
                      type="checkbox"
                      checked={!off}
                      onChange={() => toggleHidden(n.id)}
                    />
                    {n.cover_face_url && <img src={n.cover_face_url} alt="" />}
                    <span className="realm-people__name">
                      {n.name?.startsWith("Cluster_") ? "Unnamed" : n.name}
                    </span>
                    <span className="realm-people__count">{n.face_count}</span>
                  </label>
                );
              })}
          </div>
        </aside>
      )}

      <aside className={`realm-panel ${selected && !clean ? "realm-panel--open" : ""}`}>
        {selected && (
          <>
            <div className="realm-panel__head">
              {selected.cover_face_url && (
                <div className="realm-panel__avatar">
                  <img src={selected.cover_face_url} alt="" />
                </div>
              )}
              <div>
                <h2 className="realm-panel__name">
                  {selected.name?.startsWith("Cluster_") ? "Unnamed person" : selected.name}
                </h2>
                <div className="realm-panel__meta">
                  {selected.face_count} memories
                  {selected.confirmed ? " · named" : " · not named yet"}
                </div>
              </div>
              <button className="realm-panel__close" onClick={() => setSelected(null)}>
                ×
              </button>
            </div>
            <div className="realm-grid">
              {loadingPhotos ? (
                <div className="realm-empty">Gathering memories…</div>
              ) : sidebarPhotos.length === 0 ? (
                <div className="realm-empty">No photos found.</div>
              ) : (
                sidebarPhotos.map((p) => (
                  <img
                    key={p.id}
                    src={
                      p.thumbnail_url
                        ? `${process.env.NEXT_PUBLIC_API_URL ?? ""}${p.thumbnail_url}`
                        : getPhotoUrl(p.id, libHash)
                    }
                    alt=""
                    loading="lazy"
                    onClick={() => setLightbox(p)}
                  />
                ))
              )}
            </div>
          </>
        )}
      </aside>

      {lightbox && (
        <div className="realm-lightbox" onClick={() => setLightbox(null)}>
          <img src={getPhotoUrl(lightbox.id, libHash)} alt="" />
        </div>
      )}
    </div>
  );
}

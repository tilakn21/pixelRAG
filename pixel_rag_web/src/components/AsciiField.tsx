"use client";

import { useEffect, useId, useState } from "react";

interface AsciiFieldProps {
  variant?: "iris" | "wave" | "swirl" | "horizon";
  tone?: "cobalt" | "silver" | "obsidian";
  className?: string;
  caption?: string;
  scale?: "hero" | "inline";
}

interface GlyphNode {
  x: number;
  y: number;
  base: number;
  driftX: number;
  driftY: number;
  weight: number;
  seed: number;
}

const SPARSE = [".", ",", "'", "`"];
const MEDIUM = [":", ";", "-", "=", "+", "*"];
const DENSE = ["#", "%", "@", "&"];
const VIEW_BOX = { width: 1000, height: 620 };

function createIrisNodes(): GlyphNode[] {
  const nodes: GlyphNode[] = [];

  for (let ring = 0; ring < 7; ring += 1) {
    const radiusX = 112 + ring * 62;
    const radiusY = 76 + ring * 42;
    const count = 18 + ring * 12;

    for (let index = 0; index < count; index += 1) {
      const angle = (Math.PI * 2 * index) / count;
      nodes.push({
        x: 500 + Math.cos(angle) * radiusX,
        y: 310 + Math.sin(angle) * radiusY,
        base: ring > 4 ? 1 : 0,
        driftX: Math.cos(angle * 2.2) * 6,
        driftY: Math.sin(angle * 1.7) * 5,
        weight: 0.34 + ring * 0.08,
        seed: ring * 100 + index,
      });
    }
  }

  for (let index = 0; index < 54; index += 1) {
    const angle = (Math.PI * 2 * index) / 54;
    const radius = 70 + (index % 6) * 8;
    nodes.push({
      x: 500 + Math.cos(angle) * radius,
      y: 310 + Math.sin(angle) * radius * 0.68,
      base: 1,
      driftX: Math.sin(angle * 3) * 8,
      driftY: Math.cos(angle * 2) * 5,
      weight: 0.92,
      seed: 800 + index,
    });
  }

  return nodes;
}

function createWaveNodes(): GlyphNode[] {
  const nodes: GlyphNode[] = [];

  for (let row = 0; row < 13; row += 1) {
    for (let col = 0; col < 28; col += 1) {
      nodes.push({
        x: 78 + col * 31,
        y: 110 + row * 28 + Math.sin(col * 0.35) * 12,
        base: row > 5 ? 1 : 0,
        driftX: 0,
        driftY: 10 + (row % 4) * 3,
        weight: 0.3 + row * 0.04,
        seed: row * 60 + col,
      });
    }
  }

  return nodes;
}

function createSwirlNodes(): GlyphNode[] {
  const nodes: GlyphNode[] = [];

  for (let index = 0; index < 220; index += 1) {
    const angle = index * 0.29;
    const radius = 22 + index * 2.1;
    nodes.push({
      x: 500 + Math.cos(angle) * radius * 0.72,
      y: 310 + Math.sin(angle) * radius * 0.48,
      base: index > 70 ? 1 : 0,
      driftX: Math.sin(angle * 2.2) * 7,
      driftY: Math.cos(angle * 1.8) * 6,
      weight: 0.4 + (index % 9) * 0.05,
      seed: 1500 + index,
    });
  }

  return nodes;
}

function createHorizonNodes(): GlyphNode[] {
  const nodes: GlyphNode[] = [];

  for (let index = 0; index < 36; index += 1) {
    nodes.push({
      x: 46 + index * 26,
      y: 340 + Math.sin(index * 0.55) * 8,
      base: 1,
      driftX: 3,
      driftY: 4,
      weight: 0.8,
      seed: 2000 + index,
    });
  }

  for (let row = 0; row < 6; row += 1) {
    for (let col = 0; col < 24; col += 1) {
      nodes.push({
        x: 120 + col * 32,
        y: 170 + row * 42 + Math.sin(col * 0.45 + row) * 10,
        base: row > 2 ? 1 : 0,
        driftX: 0,
        driftY: 7,
        weight: 0.26 + row * 0.06,
        seed: 2200 + row * 60 + col,
      });
    }
  }

  return nodes;
}

const NODE_MAP: Record<NonNullable<AsciiFieldProps["variant"]>, GlyphNode[]> = {
  iris: createIrisNodes(),
  wave: createWaveNodes(),
  swirl: createSwirlNodes(),
  horizon: createHorizonNodes(),
};

function getGlyph(pool: string[], seed: number) {
  return pool[Math.abs(seed) % pool.length] ?? ".";
}

export default function AsciiField({
  variant = "iris",
  tone = "cobalt",
  className = "",
  caption,
  scale = "inline",
}: AsciiFieldProps) {
  const [pointer, setPointer] = useState({ x: 0.5, y: 0.5, active: false });
  const [phase, setPhase] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);
  const gradientId = useId().replace(/:/g, "");
  const nodes = NODE_MAP[variant];

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(mediaQuery.matches);
    update();
    mediaQuery.addEventListener("change", update);

    return () => mediaQuery.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (reducedMotion) return;

    const interval = window.setInterval(() => {
      setPhase((current) => current + 1);
    }, 110);

    return () => window.clearInterval(interval);
  }, [reducedMotion]);

  return (
    <figure
      className={`ascii-field ascii-field--${tone} ascii-field--${scale} ${className}`.trim()}
      onPointerMove={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        setPointer({
          x: (event.clientX - bounds.left) / bounds.width,
          y: (event.clientY - bounds.top) / bounds.height,
          active: true,
        });
      }}
      onPointerLeave={() => setPointer({ x: 0.5, y: 0.5, active: false })}
    >
      <svg
        className="ascii-field__svg"
        viewBox={`0 0 ${VIEW_BOX.width} ${VIEW_BOX.height}`}
        role="img"
        aria-label={caption ?? `${variant} ascii artwork`}
      >
        <defs>
          <radialGradient id={`${gradientId}-wash`} cx="50%" cy="50%" r="68%">
            <stop offset="0%" stopColor="currentColor" stopOpacity={tone === "cobalt" ? 0.22 : 0.12} />
            <stop offset="72%" stopColor="currentColor" stopOpacity={0.04} />
            <stop offset="100%" stopColor="currentColor" stopOpacity={0} />
          </radialGradient>
          <linearGradient id={`${gradientId}-glyph`} x1="0%" x2="100%" y1="0%" y2="100%">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.36" />
            <stop offset="45%" stopColor="currentColor" stopOpacity="0.94" />
            <stop offset="72%" stopColor={tone === "cobalt" ? "#f0b56d" : "currentColor"} stopOpacity={tone === "cobalt" ? 0.76 : 0.72} />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0.25" />
          </linearGradient>
          <filter id={`${gradientId}-blur`} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="28" />
          </filter>
        </defs>

        <ellipse
          cx={500 + (pointer.x - 0.5) * 80}
          cy={310 + (pointer.y - 0.5) * 56}
          rx={pointer.active ? 290 : 250}
          ry={pointer.active ? 186 : 160}
          fill={`url(#${gradientId}-wash)`}
          filter={`url(#${gradientId}-blur)`}
        />

        <g className="ascii-field__grid">
          {nodes.map((node, index) => {
            const pointerX = pointer.x * VIEW_BOX.width;
            const pointerY = pointer.y * VIEW_BOX.height;
            const distance = Math.hypot(node.x - pointerX, node.y - pointerY);
            const focus = pointer.active ? Math.max(0, 1 - distance / 250) : 0;
            const pulse = reducedMotion ? 0 : Math.sin(phase * 0.16 + node.seed * 0.13);
            const driftScale = pointer.active ? 1 + focus * 0.8 : 0.55;
            const x = node.x + (reducedMotion ? 0 : pulse * node.driftX * driftScale);
            const y = node.y + (reducedMotion ? 0 : pulse * node.driftY * driftScale);
            const density = node.base + (focus > 0.52 ? 2 : focus > 0.18 ? 1 : 0);
            const glyph =
              density >= 3
                ? getGlyph(DENSE, node.seed + phase + index)
                : density === 2
                  ? getGlyph(MEDIUM, node.seed + phase + index)
                  : getGlyph(SPARSE, node.seed + index);
            const opacity = 0.16 + node.weight * 0.22 + focus * 0.45 + Math.max(0, pulse) * 0.06;
            const fontSize =
              scale === "hero" ? 12 + node.weight * 4 + focus * 5 : 9 + node.weight * 3 + focus * 3;

            return (
              <text
                key={`${node.seed}-${index}`}
                x={x}
                y={y}
                fill={`url(#${gradientId}-glyph)`}
                fillOpacity={Math.min(opacity, 0.98)}
                fontSize={fontSize}
                textAnchor="middle"
                dominantBaseline="middle"
              >
                {glyph}
              </text>
            );
          })}
        </g>
      </svg>

      {caption ? <figcaption>{caption}</figcaption> : null}
    </figure>
  );
}

"use client";

import { useEffect, useState } from "react";

interface FullscreenLoaderProps {
  isLoading: boolean;
  phase: string;
}

export default function FullscreenLoader({ isLoading, phase }: FullscreenLoaderProps) {
  const [shouldRender, setShouldRender] = useState(false);
  const [isExiting, setIsExiting] = useState(false);

  useEffect(() => {
    if (isLoading) {
      setShouldRender(true);
      setIsExiting(false);
    } else if (shouldRender) {
      setIsExiting(true);
      const timer = setTimeout(() => {
        setShouldRender(false);
        setIsExiting(false);
      }, 900); // Slightly more than the 0.8s CSS duration
      return () => clearTimeout(timer);
    }
  }, [isLoading, shouldRender]);

  if (!shouldRender) return null;

  return (
    <div className={`fullscreen-loader ${isExiting ? "fullscreen-loader--exiting" : "fullscreen-loader--entering"}`}>
      <video
        autoPlay
        loop
        muted
        playsInline
      >
        <source src="/animations gifs/loading_fullscreen_animation.mp4" type="video/mp4" />
      </video>
      
      <div className="fullscreen-loader__content">
        <span style={{ fontFamily: "var(--font-pixel)", fontSize: "0.8rem", color: "var(--sun-yellow)", marginBottom: "10px", display: "block" }}>
          [ COMPUTATIONAL_FLUX ]
        </span>
        <h2 style={{ fontFamily: "var(--font-pixel)", fontSize: "clamp(1.5rem, 5vw, 3rem)", margin: 0, textShadow: "4px 4px 0 #000", textTransform: "uppercase" }}>
          {phase}
        </h2>
        <div style={{ marginTop: "20px", display: "flex", justifyContent: "center", gap: "10px" }}>
          <div className="spinner" style={{ borderColor: "var(--sun-yellow)", borderWidth: "3px" }} />
        </div>
      </div>

      <style jsx>{`
        .fullscreen-loader__content {
           animation: fade-in 0.4s ease-out 0.3s backwards;
        }
      `}</style>
    </div>
  );
}

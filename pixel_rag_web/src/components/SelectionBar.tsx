// pixel_rag_web/src/components/SelectionBar.tsx
"use client";

import { useEffect, useState } from "react";
import {
  deletePhotos,
  exportAlbum,
  revealFolder,
  zipAlbum,
  type DeleteMode,
  type ExportSize,
} from "@/lib/api";
import {
  MAX_SHARE_FILES,
  canShareFiles,
  downloadBlob,
  loadPhotoFiles,
  openWhatsApp,
  shareAvailability,
  shareFiles,
  type ShareAvailability,
} from "@/lib/share";

interface SelectionBarProps {
  selected: number[];
  totalAvailable: number;
  onSelectAll: () => void;
  onClear: () => void;
  onDone: (msg: string) => void;
  libHash?: string;
  /** When set, "select all" can cover an entire cluster, not just loaded photos. */
  personId?: number;
}

const MODE_COPY: Record<DeleteMode, { label: string; blurb: string; danger: boolean }> = {
  trash: {
    label: "Move to Trash",
    blurb:
      "Files go to the Trash on the drive they live on (<drive>/.Trashes) — not your Mac's Trash, so emptying the Mac Trash won't free the space.",
    danger: false,
  },
  permanent: {
    label: "Delete permanently",
    blurb: "Files are erased immediately. This cannot be undone.",
    danger: true,
  },
  forget: {
    label: "Remove from PixelRAG only",
    blurb: "The photo leaves the library but the file on disk is left untouched.",
    danger: false,
  },
};

export default function SelectionBar({
  selected,
  totalAvailable,
  onSelectAll,
  onClear,
  onDone,
  libHash,
  personId,
}: SelectionBarProps) {
  const [busy, setBusy] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [showFolder, setShowFolder] = useState(false);
  const [mode, setMode] = useState<DeleteMode>("trash");
  const [confirmText, setConfirmText] = useState("");
  const [folderName, setFolderName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const [showShare, setShowShare] = useState(false);
  const [destination, setDestination] = useState<"library" | "desktop" | "downloads">("library");
  const [openAfter, setOpenAfter] = useState(true);
  const [zipSize, setZipSize] = useState<ExportSize>("web");
  const [caption, setCaption] = useState("");
  const [readyFiles, setReadyFiles] = useState<File[] | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

  // Probed in an effect rather than during render: it reads `navigator` and
  // `window.isSecureContext`, which do not exist on the server, and deciding
  // during render would produce a hydration mismatch.
  const [avail, setAvail] = useState<ShareAvailability>({ available: false, reason: null });
  useEffect(() => setAvail(shareAvailability()), []);

  const n = selected.length;
  if (n === 0) return null;

  // Permanent deletion is irreversible, so it needs typed confirmation rather
  // than a single click that could be a misfire.
  const needsTyped = mode === "permanent";
  const typedOk = !needsTyped || confirmText.trim().toUpperCase() === "DELETE";

  const runDelete = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await deletePhotos({ photo_ids: selected, mode }, libHash);
      setShowDelete(false);
      setConfirmText("");
      onDone(
        `${r.removed_from_library} removed from library` +
          (r.files_affected ? ` · ${r.files_affected} files ${mode === "permanent" ? "erased" : "trashed"}` : "") +
          (r.files_already_missing ? ` · ${r.files_already_missing} already missing` : "") +
          (r.errors.length ? ` · ${r.errors.length} errors` : "")
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  const runExport = async () => {
    if (!folderName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await exportAlbum(
        { photo_ids: selected, name: folderName.trim(), destination },
        libHash
      );
      // Reveal is best-effort: the export already succeeded, so a Finder that
      // refuses to open must not be reported as a failed export.
      let revealed = false;
      if (openAfter) {
        try {
          await revealFolder(r.folder, libHash);
          revealed = true;
        } catch {
          /* non-fatal */
        }
      }
      setShowFolder(false);
      setFolderName("");
      onDone(
        `Copied ${r.copied} photos to ${r.folder}` +
          (r.skipped_missing ? ` · ${r.skipped_missing} skipped (file missing)` : "") +
          (openAfter && !revealed ? " · could not open Finder" : "")
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(false);
    }
  };

  const runZip = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await zipAlbum(
        { photo_ids: selected, name: folderName.trim() || "PixelRAG", size: zipSize },
        libHash
      );
      downloadBlob(r.blob, r.filename);
      setShowFolder(false);
      onDone(
        `Downloaded ${r.added} photo${r.added === 1 ? "" : "s"} as ${r.filename}` +
          (r.skipped ? ` · ${r.skipped} skipped` : "")
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setBusy(false);
    }
  };

  // Files are fetched here and held in state so the share call itself can run
  // synchronously from the next click. Awaiting megabytes of fetches and then
  // calling navigator.share loses the user gesture and Safari rejects it.
  const prepareShare = async () => {
    setBusy(true);
    setError(null);
    setProgress({ done: 0, total: Math.min(selected.length, MAX_SHARE_FILES) });
    try {
      const files = await loadPhotoFiles(selected, libHash, (done, total) =>
        setProgress({ done, total })
      );
      if (files.length === 0) throw new Error("None of the selected photos could be read.");
      if (!canShareFiles(files)) {
        throw new Error("This browser will not share these files. Use Download instead.");
      }
      setReadyFiles(files);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not prepare the photos");
    } finally {
      setProgress(null);
      setBusy(false);
    }
  };

  const doShare = async () => {
    if (!readyFiles) return;
    try {
      const outcome = await shareFiles(readyFiles, caption.trim());
      if (outcome === "shared") {
        setShowShare(false);
        setReadyFiles(null);
        onDone(`Shared ${readyFiles.length} photo${readyFiles.length === 1 ? "" : "s"}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Share failed");
    }
  };

  const downloadThenWhatsApp = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await zipAlbum(
        { photo_ids: selected, name: "PixelRAG", size: zipSize },
        libHash
      );
      downloadBlob(r.blob, r.filename);
      openWhatsApp(caption.trim());
      setShowShare(false);
      onDone(`Downloaded ${r.added} photos — attach them in WhatsApp`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setBusy(false);
    }
  };

  const closeAll = () => {
    setShowDelete(false);
    setShowFolder(false);
    setShowShare(false);
    setReadyFiles(null);
    setProgress(null);
    setError(null);
  };

  const chip = (bg: string, color: string) => ({
    background: bg,
    color,
    border: "var(--border-thick)",
    borderRadius: "10px",
    padding: "8px 14px",
    fontFamily: "var(--font-pixel)",
    fontSize: "0.85rem",
    cursor: busy ? "wait" : "pointer",
    opacity: busy ? 0.6 : 1,
  });

  return (
    <>
      <div
        style={{
          position: "fixed",
          bottom: 22,
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: 120,
          display: "flex",
          alignItems: "center",
          gap: 14,
          background: "var(--obsidian)",
          color: "#fff",
          padding: "14px 20px",
          borderRadius: 16,
          border: "var(--border-thick)",
          boxShadow: "0 10px 30px rgba(0,0,0,.45)",
          flexWrap: "wrap",
          maxWidth: "94vw",
        }}
      >
        <span style={{ fontFamily: "var(--font-pixel)", color: "var(--sun-yellow)", fontSize: "1.05rem" }}>
          [{n} SELECTED]
        </span>
        {n < totalAvailable && (
          <button style={chip("#fff", "#000")} onClick={onSelectAll} disabled={busy}>
            SELECT_ALL{personId ? "_IN_CLUSTER" : ""} ({totalAvailable})
          </button>
        )}
        <button style={chip("#25D366", "#03310f")} onClick={() => setShowShare(true)} disabled={busy}>
          SHARE
        </button>
        <button style={chip("var(--electric-blue)", "#fff")} onClick={() => setShowFolder(true)} disabled={busy}>
          EXPORT
        </button>
        <button style={chip("#fee2e2", "#991b1b")} onClick={() => setShowDelete(true)} disabled={busy}>
          DELETE
        </button>
        <button
          style={{ ...chip("transparent", "#fff"), border: "none", textDecoration: "underline" }}
          onClick={onClear}
          disabled={busy}
        >
          CANCEL
        </button>
      </div>

      {(showDelete || showFolder || showShare) && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,.7)",
            zIndex: 200,
            display: "grid",
            placeItems: "center",
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget && !busy) closeAll();
          }}
        >
          <div
            style={{
              background: "#fff",
              borderRadius: 18,
              padding: 30,
              width: "min(520px, 92vw)",
              border: "var(--border-thick)",
              boxShadow: "8px 8px 0 var(--obsidian)",
            }}
          >
            {showDelete ? (
              <>
                <h2 style={{ fontFamily: "var(--font-pixel)", fontSize: "1.25rem", margin: 0 }}>
                  DELETE {n} PHOTO{n === 1 ? "" : "S"}
                </h2>
                <div style={{ display: "flex", flexDirection: "column", gap: 10, margin: "18px 0" }}>
                  {(Object.keys(MODE_COPY) as DeleteMode[]).map((m) => (
                    <label
                      key={m}
                      style={{
                        display: "flex",
                        gap: 10,
                        alignItems: "flex-start",
                        padding: 12,
                        borderRadius: 10,
                        border: mode === m ? "2px solid var(--electric-purple)" : "1px solid #ddd",
                        cursor: "pointer",
                        background: mode === m ? "#faf7ff" : "#fff",
                      }}
                    >
                      <input
                        type="radio"
                        checked={mode === m}
                        onChange={() => {
                          setMode(m);
                          setConfirmText("");
                        }}
                        style={{ marginTop: 3 }}
                      />
                      <span>
                        <strong style={{ fontFamily: "var(--font-pixel)", fontSize: "0.9rem" }}>
                          {MODE_COPY[m].label}
                        </strong>
                        <div style={{ fontSize: "0.8rem", color: "#555", marginTop: 4, lineHeight: 1.45 }}>
                          {MODE_COPY[m].blurb}
                        </div>
                      </span>
                    </label>
                  ))}
                </div>

                {needsTyped && (
                  <div style={{ marginBottom: 14 }}>
                    <div style={{ fontSize: "0.8rem", color: "#991b1b", marginBottom: 6 }}>
                      Type <strong>DELETE</strong> to confirm permanent erasure of {n} file{n === 1 ? "" : "s"}.
                    </div>
                    <input
                      value={confirmText}
                      onChange={(e) => setConfirmText(e.target.value)}
                      placeholder="DELETE"
                      style={{
                        width: "100%",
                        padding: "10px 12px",
                        borderRadius: 8,
                        border: "var(--border-thick)",
                        fontFamily: "var(--font-pixel)",
                        boxSizing: "border-box",
                      }}
                    />
                  </div>
                )}

                {error && (
                  <div style={{ color: "#dc2626", fontSize: "0.85rem", marginBottom: 12 }}>⚠ {error}</div>
                )}

                <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
                  <button
                    style={chip("transparent", "#000")}
                    onClick={() => {
                      setShowDelete(false);
                      setError(null);
                    }}
                    disabled={busy}
                  >
                    CANCEL
                  </button>
                  <button
                    style={{
                      ...chip(typedOk ? "#991b1b" : "#ddd", "#fff"),
                      cursor: typedOk && !busy ? "pointer" : "not-allowed",
                    }}
                    onClick={runDelete}
                    disabled={busy || !typedOk}
                  >
                    {busy ? "WORKING..." : MODE_COPY[mode].label.toUpperCase()}
                  </button>
                </div>
              </>
            ) : showFolder ? (
              <>
                <h2 style={{ fontFamily: "var(--font-pixel)", fontSize: "1.25rem", margin: 0 }}>
                  EXPORT {n} PHOTO{n === 1 ? "" : "S"}
                </h2>
                <p style={{ fontSize: "0.85rem", color: "#555", marginTop: 10, lineHeight: 1.5 }}>
                  Copies the files into a real folder you can open in Finder. Originals are never
                  moved or changed, and exported folders are skipped by future syncs.
                </p>
                <input
                  autoFocus
                  value={folderName}
                  onChange={(e) => setFolderName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && runExport()}
                  placeholder="Folder name (e.g. Goa Trip 2024)"
                  style={{
                    width: "100%",
                    padding: "12px 14px",
                    borderRadius: 10,
                    border: "var(--border-thick)",
                    fontFamily: "var(--font-pixel)",
                    margin: "16px 0 12px",
                    boxSizing: "border-box",
                  }}
                />

                <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
                  {([
                    ["library", "Library drive"],
                    ["desktop", "Desktop"],
                    ["downloads", "Downloads"],
                  ] as const).map(([key, label]) => (
                    <button
                      key={key}
                      onClick={() => setDestination(key)}
                      style={{
                        padding: "7px 12px",
                        borderRadius: 8,
                        cursor: "pointer",
                        fontSize: "0.78rem",
                        fontFamily: "var(--font-mono)",
                        border:
                          destination === key
                            ? "2px solid var(--electric-purple)"
                            : "1px solid #ddd",
                        background: destination === key ? "#faf7ff" : "#fff",
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                <label
                  style={{
                    display: "flex",
                    gap: 8,
                    alignItems: "center",
                    fontSize: "0.82rem",
                    color: "#444",
                    marginBottom: 14,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={openAfter}
                    onChange={(e) => setOpenAfter(e.target.checked)}
                  />
                  Open the folder in Finder when it is ready
                </label>

                <div
                  style={{
                    borderTop: "1px dashed #ddd",
                    paddingTop: 12,
                    fontSize: "0.8rem",
                    color: "#555",
                    lineHeight: 1.5,
                  }}
                >
                  Not sitting at this Mac? Download the selection instead — that is the only
                  export that works from a phone, which has no folder on this machine to write to.
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10 }}>
                    {([
                      ["web", "Smaller (2048px)"],
                      ["original", "Originals"],
                    ] as const).map(([key, label]) => (
                      <button
                        key={key}
                        onClick={() => setZipSize(key)}
                        style={{
                          padding: "6px 10px",
                          borderRadius: 8,
                          cursor: "pointer",
                          fontSize: "0.72rem",
                          fontFamily: "var(--font-mono)",
                          border: zipSize === key ? "2px solid #111" : "1px solid #ddd",
                          background: "#fff",
                        }}
                      >
                        {label}
                      </button>
                    ))}
                    <button
                      style={{ ...chip("#111", "#fff"), fontSize: "0.72rem", padding: "7px 12px" }}
                      onClick={runZip}
                      disabled={busy}
                    >
                      {busy ? "ZIPPING..." : "DOWNLOAD_ZIP"}
                    </button>
                  </div>
                </div>

                {error && (
                  <div style={{ color: "#dc2626", fontSize: "0.85rem", margin: "12px 0" }}>⚠ {error}</div>
                )}
                <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 16 }}>
                  <button style={chip("transparent", "#000")} onClick={closeAll} disabled={busy}>
                    CANCEL
                  </button>
                  <button
                    style={chip("var(--electric-blue)", "#fff")}
                    onClick={runExport}
                    disabled={busy || !folderName.trim()}
                  >
                    {busy ? "COPYING..." : "CREATE_FOLDER"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <h2 style={{ fontFamily: "var(--font-pixel)", fontSize: "1.25rem", margin: 0 }}>
                  SHARE {n} PHOTO{n === 1 ? "" : "S"}
                </h2>

                <textarea
                  value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                  placeholder="Caption (optional)"
                  rows={2}
                  style={{
                    width: "100%",
                    padding: "12px 14px",
                    borderRadius: 10,
                    border: "var(--border-thick)",
                    fontFamily: "inherit",
                    fontSize: "0.9rem",
                    margin: "16px 0 14px",
                    boxSizing: "border-box",
                    resize: "vertical",
                  }}
                />

                {avail.available ? (
                  <>
                    <p style={{ fontSize: "0.85rem", color: "#555", lineHeight: 1.5, margin: 0 }}>
                      Opens your device&apos;s share sheet with the photos attached — WhatsApp,
                      Messages, Mail and AirDrop all appear there.
                      {n > MAX_SHARE_FILES && (
                        <>
                          {" "}
                          <strong>
                            Only the first {MAX_SHARE_FILES} of {n} will be included
                          </strong>{" "}
                          — share sheets refuse large batches.
                        </>
                      )}
                    </p>
                    {progress && (
                      <div style={{ fontSize: "0.8rem", color: "#555", marginTop: 12 }}>
                        Preparing {progress.done} / {progress.total}…
                      </div>
                    )}
                    {error && (
                      <div style={{ color: "#dc2626", fontSize: "0.85rem", marginTop: 12 }}>⚠ {error}</div>
                    )}
                    <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 18 }}>
                      <button style={chip("transparent", "#000")} onClick={closeAll} disabled={busy}>
                        CANCEL
                      </button>
                      {readyFiles ? (
                        <button style={chip("#25D366", "#03310f")} onClick={doShare}>
                          OPEN_SHARE_SHEET ({readyFiles.length})
                        </button>
                      ) : (
                        <button
                          style={chip("#25D366", "#03310f")}
                          onClick={prepareShare}
                          disabled={busy}
                        >
                          {busy ? "PREPARING..." : "PREPARE_PHOTOS"}
                        </button>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <p style={{ fontSize: "0.85rem", color: "#555", lineHeight: 1.5, margin: 0 }}>
                      No share sheet here, so this is two steps: the photos download, then WhatsApp
                      opens with your caption ready and you attach them.
                    </p>
                    {avail.reason && (
                      <p
                        style={{
                          fontSize: "0.78rem",
                          color: "#777",
                          lineHeight: 1.5,
                          marginTop: 8,
                          paddingLeft: 10,
                          borderLeft: "3px solid #eee",
                        }}
                      >
                        {avail.reason}
                      </p>
                    )}
                    <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 14 }}>
                      {([
                        ["web", "Smaller (2048px)"],
                        ["original", "Originals"],
                      ] as const).map(([key, label]) => (
                        <button
                          key={key}
                          onClick={() => setZipSize(key)}
                          style={{
                            padding: "6px 10px",
                            borderRadius: 8,
                            cursor: "pointer",
                            fontSize: "0.72rem",
                            fontFamily: "var(--font-mono)",
                            border: zipSize === key ? "2px solid #111" : "1px solid #ddd",
                            background: "#fff",
                          }}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    {error && (
                      <div style={{ color: "#dc2626", fontSize: "0.85rem", marginTop: 12 }}>⚠ {error}</div>
                    )}
                    <div
                      style={{
                        display: "flex",
                        gap: 10,
                        justifyContent: "flex-end",
                        marginTop: 18,
                        flexWrap: "wrap",
                      }}
                    >
                      <button style={chip("transparent", "#000")} onClick={closeAll} disabled={busy}>
                        CANCEL
                      </button>
                      <button
                        style={{ ...chip("#fff", "#000"), fontSize: "0.75rem" }}
                        onClick={() => openWhatsApp(caption.trim())}
                        disabled={busy}
                      >
                        CAPTION_ONLY
                      </button>
                      <button
                        style={chip("#25D366", "#03310f")}
                        onClick={downloadThenWhatsApp}
                        disabled={busy}
                      >
                        {busy ? "PREPARING..." : "DOWNLOAD + WHATSAPP"}
                      </button>
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

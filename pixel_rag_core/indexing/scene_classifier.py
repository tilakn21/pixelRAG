# pixel_rag_core/indexing/scene_classifier.py
"""
Routed scene classification (v2).

Design, and why it looks like this — every number below was measured on this
user's own library, not assumed (see CONTEXT.md §15):

  * The old flat 14-way CLIP argmax scored 33% on a hand-labeled sample and
    misfiled 340 of 476 face-bearing photos (71%) as landscape/event/vehicle.
    Confidences sat at 0.11-0.17 against a 0.071 uniform baseline, i.e. the
    distribution was nearly flat and argmax was close to arbitrary.
  * Scaling the model plateaued (B-16 and L-14 both 56.9%), which said the
    bottleneck was the QUESTION, not capacity: CLIP was being asked "is this a
    person?" while a face detector was already running upstream.
  * Two fixes, measured independently:
      - model/weights: ViT-L-14-quickgelu/dfn2b -> 88.2%. open_clip pairs the
        'openai' tag with QuickGELU; the plain 'ViT-L-14' name silently used
        standard GELU, so production had mismatched activations.
      - face-first routing: 25.0% -> 94.4% on already-indexed face data.

Routing order (first decisive rule wins):
  1. faces  : any detected face  -> 'people'          [user: never miss a person]
  2. clip   : CLIP's top label if it clears threshold
  3. unsorted: below threshold   -> review bucket      [user: don't guess silently]

`scene_secondary` always stores CLIP's best NON-people label, so a beach photo
containing people stays findable as a beach photo without splitting its primary
bucket. `scene_model` records the classifier version so a future upgrade can
reclassify only what is stale.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# HEIC/HEIF support. face_indexer also registers this, but scene classification
# must not depend on another module having been imported first — standalone and
# reclassify-only runs would otherwise fail every iPhone photo.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

# ── Model selection ──────────────────────────────────────────────────────────
# Benchmarked on 51 hand-labeled images from this library
# (scratch/eval_scene/benchmark_clip.py):
#     ViT-B-32/openai            33.3%   <- previous production default
#     ViT-B-16/openai            56.9%
#     ViT-L-14/openai            56.9%
#     ViT-L-14-quickgelu/dfn2b   88.2%   <- current default
CLIP_MODEL = os.environ.get("PIXELRAG_CLIP_MODEL", "ViT-L-14-quickgelu")
CLIP_PRETRAINED = os.environ.get("PIXELRAG_CLIP_PRETRAINED", "dfn2b")
# Bump PROMPT_VERSION whenever CATEGORY_PROMPTS changes: it flows into
# SCENE_MODEL_TAG, which is what marks rows stale for reclassification. Image
# embeddings are prompt-independent, so a prompt change only requires
# reroute_from_embeddings() — seconds — not a re-inference pass.
PROMPT_VERSION = "p2"
SCENE_MODEL_TAG = f"{CLIP_MODEL}/{CLIP_PRETRAINED}+routed-v2-{PROMPT_VERSION}"

# Batch size for MPS/CPU inference.
CLIP_BATCH = int(os.environ.get("PIXELRAG_CLIP_BATCH", "16"))

# Softmax temperature over cosine similarities. CLIP's own learned logit_scale
# is ~100; the previous value of 15.0 flattened the distribution so severely
# that every photo tripped the low-confidence flag.
SOFTMAX_TEMP = float(os.environ.get("PIXELRAG_SCENE_TEMP", "100.0"))

# Below this top-1 probability the photo goes to the 'unsorted' review bucket
# instead of being silently filed under a wrong category.
CONFIDENCE_THRESHOLD = float(os.environ.get("PIXELRAG_SCENE_THRESHOLD", "0.30"))

UNSORTED = "unsorted"

# ── Category taxonomy with prompt ensembling ─────────────────────────────────
# Multiple prompts per category are encoded and averaged into one robust text
# embedding (standard CLIP zero-shot technique from the original OpenAI paper).
CATEGORY_PROMPTS = {
    "landscape": [
        "a photo of a landscape, nature, mountains, or outdoors",
        "a scenic nature view with trees, fields, or sky",
        "an outdoor landscape photograph",
    ],
    "document": [
        "a photo of a document, receipt, text page, or paperwork",
        "a photograph of printed or handwritten text on paper",
        "a scanned document, form, certificate, or identity card",
    ],
    "food": [
        "a photo of food, a meal, a plate of food, or a beverage",
        "a photograph of a dish, snack, or drink on a table",
        "a close-up photo of a prepared meal or cuisine",
    ],
    "architecture": [
        "a photo of a building, city street, or architecture",
        "a photograph of urban architecture, a monument, or a structure",
        "a photo of a house, temple, bridge, or skyscraper",
    ],
    "people": [
        "a photo of a person, people, human body, selfie, portrait, or silhouette",
        "a photograph showing one or more people, faces, or human figures",
        "a portrait, selfie, group photo, or candid shot of people",
    ],
    "animal": [
        "a photo of an animal, pet, cat, dog, or wildlife",
        "a photograph of a domestic or wild animal",
        "a close-up photo of a pet, bird, or zoo animal",
    ],
    "vehicle": [
        "a photo of a car, truck, motorbike, bicycle, or other vehicle",
        "a photograph of a vehicle on a road or parked",
        "a photo of transportation or automobile",
    ],
    "screenshot": [
        "a screenshot of a phone screen, website, or computer application",
        "a digital screenshot from a mobile app or desktop program",
        "a screen capture showing a user interface, chat, or social media feed",
    ],
    "art": [
        "a photo of art, a painting, a sketch, or an illustration",
        "a photograph of a piece of artwork, mural, or sculpture",
        "a photo of a drawing, painting, or creative artwork",
    ],
    "event": [
        "a photo of an event, party, concert, or gathering of people",
        "a photograph from a celebration, wedding, festival, or ceremony",
        "a photo of a social gathering, conference, or live performance",
    ],
    "night": [
        "a photo of the night sky, stars, moon, or dark street lights at night",
        "a nighttime photograph with city lights or starry sky",
        "a low-light or night photograph",
    ],
    "object": [
        "a photo of a specific object, tech, tool, or still life",
        "a close-up photograph of a single object or gadget",
        "a product photo or still life composition",
    ],
    "map_chart": [
        "a photo of a map, chart, diagram, or infographic",
        "a photograph of a graph, flowchart, or data visualization",
        "a photo of a geographical map or statistical chart",
    ],
    "other": [
        "a photo of something else, abstract, or unknown",
        "an abstract or ambiguous photograph",
        "a miscellaneous photo that doesn't fit standard categories",
    ],
}

CATEGORIES: List[str] = list(CATEGORY_PROMPTS.keys())
_PEOPLE_IDX = CATEGORIES.index("people")

# ── People-recall channel ────────────────────────────────────────────────────
# Motivated by a measured failure, not intuition: hand-labelling the non-people
# tail showed 4/18 photos were people shots where the FACE was invisible (turned
# away, head down, occluded). The face detector returned zero, so routing fell
# through to CLIP, which described the room instead ('animal', 'night',
# 'vehicle'). Apple and Google both solve this with torso/upper-body embeddings.
#
# These prompts are a separate CHANNEL rather than extra entries in
# CATEGORY_PROMPTS["people"], because prompt ensembling averages: folding
# heterogeneous sub-concepts into one mean dilutes it. Measured directly —
# appending them to the people mean fixed 2 photos but pushed 5 others OUT of
# people (502 -> 499 net). Scored separately and combined with a max, an extra
# signal can only promote to 'people', never demote — the same reason Apple
# fuses face and torso with min(F, aF + bT).
PEOPLE_RECALL_PROMPTS = [
    "a person seen from behind or with their back to the camera",
    "a person whose face is turned away, looking down, or hidden",
    "a full-body photo of someone standing, walking, or posing",
    "a person in the foreground of the scene",
]

# Max cosine similarity against the above needed to promote a face-less photo
# to 'people'. NOT guessed — swept against the labelled misses on the real
# library (face-less photos only, n=129 non-people / 30 CLIP-people):
#
#   known-miss scores : 0.226, 0.203, 0.183, 0.164
#   non-people        : median 0.133, p90 0.187, p95 0.195
#
#   t=0.18 -> catches 3/4 misses, promotes 21/129 non-people
#   t=0.20 -> catches 2/4,        promotes  6/129
#   t=0.22 -> catches 1/4,        promotes  0/129
#
# The distributions genuinely overlap, so no threshold is clean. 0.18 is chosen
# to honour the stated product priority ("never miss a people photo — a
# landscape in People beats losing a person"). The 21 promoted photos keep their
# scene in scene_secondary, so they remain findable by scene. Raise this if
# strangers' backs start cluttering People.
#
# The weak separation is itself the argument for real torso embeddings
# (RESEARCH.md R1 full) — CLIP prompting only approximates what Apple and
# Google do with a dedicated upper-body model.
PEOPLE_RECALL_THRESHOLD = float(os.environ.get("PIXELRAG_PEOPLE_RECALL", "0.18"))

# Module-level model cache
_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None
_text_features = None
_people_recall_features = None
_device = None


def _pick_device() -> str:
    """Prefer Apple GPU; fall back to CPU. Override with PIXELRAG_CLIP_DEVICE."""
    forced = os.environ.get("PIXELRAG_CLIP_DEVICE")
    if forced:
        return forced
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _ensure_model_loaded():
    """Lazy-load CLIP and pre-encode the prompt-ensembled text embeddings."""
    global _clip_model, _clip_preprocess, _clip_tokenizer, _text_features
    global _people_recall_features, _device

    if _clip_model is not None:
        return

    import open_clip
    import torch

    _device = _pick_device()
    print(f"[PixelRAG] Loading OpenCLIP {CLIP_MODEL}/{CLIP_PRETRAINED} on {_device}...")

    model, _, preprocess = open_clip.create_model_and_transforms(
        CLIP_MODEL, pretrained=CLIP_PRETRAINED
    )
    tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
    model = model.to(_device).eval()

    ensemble = []
    with torch.no_grad():
        for cat in CATEGORIES:
            tokens = tokenizer(CATEGORY_PROMPTS[cat]).to(_device)
            feats = model.encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            avg = feats.mean(dim=0)
            avg = avg / avg.norm()
            ensemble.append(avg)

    # People-recall prompts are kept UNaveraged: each is scored independently and
    # combined with a max, so a photo matching any one of them counts.
    with torch.no_grad():
        recall_tokens = tokenizer(PEOPLE_RECALL_PROMPTS).to(_device)
        recall_feats = model.encode_text(recall_tokens)
        recall_feats = recall_feats / recall_feats.norm(dim=-1, keepdim=True)

    _clip_model = model
    _clip_preprocess = preprocess
    _clip_tokenizer = tokenizer
    _text_features = torch.stack(ensemble)
    _people_recall_features = recall_feats

    print(f"[PixelRAG] CLIP ready. {len(CATEGORIES)} categories, "
          f"{sum(len(v) for v in CATEGORY_PROMPTS.values())} prompts ensembled, "
          f"+{len(PEOPLE_RECALL_PROMPTS)} people-recall prompts.")


def _load_image(path: str):
    """Open, EXIF-orient and RGB-normalize an image. Returns (pil, w, h)."""
    from PIL import Image, ImageOps
    img = Image.open(path)
    img.load()
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img, img.size[0], img.size[1]


def _embed_batch(
    paths: List[str],
) -> Tuple[Tuple[np.ndarray, np.ndarray, Dict[str, Tuple[int, int]]], List[str]]:
    """
    Encode a batch of images.

    Returns ((probs, embeddings, dims), kept) where probs is (n, n_categories),
    embeddings is (n, dim) float32, dims maps path -> (w, h), and `kept` lists
    the paths that decoded successfully — index i in probs/embeddings
    corresponds to kept[i]. Unreadable images are dropped from all of them.
    """
    import torch

    tensors, kept, dims = [], [], {}
    for p in paths:
        try:
            img, w, h = _load_image(p)
            tensors.append(_clip_preprocess(img))
            kept.append(p)
            dims[p] = (w, h)
        except Exception as e:
            print(f"[PixelRAG] ⚠️  CLIP could not read {Path(p).name}: {e}")

    if not tensors:
        return (np.empty((0, len(CATEGORIES)), dtype=np.float32),
                np.empty((0, 0), dtype=np.float32), {}), []

    with torch.no_grad():
        x = torch.stack(tensors).to(_device)
        feats = _clip_model.encode_image(x)
        feats = feats / feats.norm(dim=-1, keepdim=True)
        sims = feats @ _text_features.T
        probs = torch.softmax(sims * SOFTMAX_TEMP, dim=-1)

    return (
        probs.cpu().numpy().astype(np.float32),
        feats.cpu().numpy().astype(np.float32),
        {k: dims[k] for k in kept},
    ), kept


def _people_recall_scores(feats: np.ndarray) -> np.ndarray:
    """Max cosine similarity of each image embedding against the people-recall
    prompts. Max, not mean, so any single matching description counts."""
    if _people_recall_features is None or feats.size == 0:
        return np.zeros(len(feats), dtype=np.float32)
    R = _people_recall_features.cpu().numpy().astype(np.float32)
    return (feats @ R.T).max(axis=1)


def _route(
    probs_row: np.ndarray,
    n_faces: int,
    people_recall: float = 0.0,
) -> Tuple[str, float, Optional[str], str]:
    """
    Apply the routing rules to one photo.

    Returns (category, confidence, secondary, source) where `source` records
    which rule decided it, so the UI and any future audit can tell a
    face-detected 'people' from a CLIP-guessed or recall-promoted one.
    """
    order = np.argsort(probs_row)[::-1]
    top_idx = int(order[0])
    top_prob = float(probs_row[top_idx])

    # Best non-people label, always retained so scene browsing still works
    # for photos whose primary bucket is 'people'.
    secondary_idx = next((int(i) for i in order if int(i) != _PEOPLE_IDX), None)
    secondary = CATEGORIES[secondary_idx] if secondary_idx is not None else None

    # Rule 1 — a detected face outranks CLIP's opinion entirely.
    if n_faces > 0:
        return "people", 1.0, secondary, "faces"

    # Rule 2 — CLIP, if it is confident enough to commit.
    if top_prob >= CONFIDENCE_THRESHOLD:
        cat = CATEGORIES[top_idx]
        if cat == "people":
            return cat, top_prob, secondary, "clip"
        # Rule 2b — people-recall override. A face-less photo that strongly
        # matches a "person with face hidden" description is promoted to
        # 'people', keeping the scene label as secondary. Purely additive: it
        # can only move photos INTO people, never out, so it cannot regress
        # the categories it does not fire on.
        if people_recall >= PEOPLE_RECALL_THRESHOLD:
            return "people", top_prob, CATEGORIES[top_idx], "clip-recall"
        return cat, top_prob, None, "clip"

    # Rule 3 — uncertain. Give people-recall one last chance before parking it.
    if people_recall >= PEOPLE_RECALL_THRESHOLD:
        return "people", top_prob, secondary, "clip-recall"
    return UNSORTED, top_prob, secondary, "unsorted"


def classify_scene(image_path: str):
    """
    Classify a single image. Kept for callers that want a one-off result
    (no DB, no face context — so this is pure CLIP, no face routing).

    Returns (category, confidence, top3_json, low_confidence, embedding_bytes).
    """
    _ensure_model_loaded()
    (probs, feats, _), kept = _embed_batch([image_path])
    if len(kept) == 0:
        return UNSORTED, 0.0, "[]", True, None

    row = probs[0]
    order = np.argsort(row)[::-1]
    top3 = [{"category": CATEGORIES[int(i)], "score": round(float(row[int(i)]), 4)}
            for i in order[:3]]
    top_cat = CATEGORIES[int(order[0])]
    top_conf = float(row[int(order[0])])
    low = top_conf < CONFIDENCE_THRESHOLD
    return top_cat, top_conf, json.dumps(top3), low, feats[0].tobytes()


def reroute_from_embeddings(
    db_path: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    shutdown_event=None,
) -> int:
    """
    Re-apply routing using the CLIP embeddings already stored in
    photo_embeddings — no image decoding, no forward pass.

    This exists because face detection runs AFTER scene classification in the
    pipeline, so the first scene pass cannot use face-first routing. Rather
    than re-running CLIP over the whole library (~1 hour for 28k photos), this
    recomputes category probabilities from the stored embedding and re-routes
    with current face counts. Turns a re-classification into seconds of SQL.

    Returns the number of photos whose category changed.
    """
    import torch

    _ensure_model_loaded()

    db_path = Path(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        rows = conn.execute("""
            SELECT p.id, p.scene_category, pe.embedding, pe.dim,
                   (SELECT COUNT(*) FROM faces f WHERE f.photo_id = p.id) AS n_faces
            FROM photos p
            JOIN photo_embeddings pe ON pe.photo_id = p.id
        """).fetchall()

        if not rows:
            print("[PixelRAG] No stored embeddings to re-route.")
            return 0

        total = len(rows)
        print(f"[PixelRAG] Re-routing {total} photos from stored embeddings "
              f"(no inference)...")

        text_np = _text_features.cpu().numpy().astype(np.float32)
        recall_np = _people_recall_features.cpu().numpy().astype(np.float32)
        changed = 0

        for i, (photo_id, old_cat, emb_blob, dim, n_faces) in enumerate(rows):
            if shutdown_event is not None and shutdown_event.is_set():
                conn.commit()
                print(f"[PixelRAG] Shutdown requested — committed {changed} updates")
                return changed

            vec = np.frombuffer(emb_blob, dtype=np.float32, count=dim)
            sims = text_np @ vec
            e = np.exp((sims - sims.max()) * SOFTMAX_TEMP)
            probs = e / e.sum()
            recall = float((recall_np @ vec).max())

            category, confidence, secondary, source = _route(probs, n_faces or 0, recall)
            order = np.argsort(probs)[::-1]
            top3 = json.dumps([
                {"category": CATEGORIES[int(j)], "score": round(float(probs[int(j)]), 4)}
                for j in order[:3]
            ])

            conn.execute(
                """UPDATE photos
                   SET scene_category = ?, scene_confidence = ?, scene_tags = ?,
                       scene_low_confidence = ?, scene_secondary = ?,
                       scene_source = ?, scene_model = ?
                   WHERE id = ?""",
                (category, confidence, top3, 1 if category == UNSORTED else 0,
                 secondary, source, SCENE_MODEL_TAG, photo_id),
            )
            if category != old_cat:
                changed += 1

            if (i + 1) % 500 == 0:
                conn.commit()
                if progress_callback:
                    progress_callback(i + 1, total, "Re-routing categories")

        conn.commit()
    finally:
        conn.close()

    print(f"[PixelRAG] Re-route complete. {changed}/{total} categories changed.")
    return changed


def classify_untagged_photos(
    db_path: str,
    limit: Optional[int] = None,
    reclassify_all: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    shutdown_event=None,
) -> int:
    """
    Classify photos using routed classification (faces -> CLIP -> unsorted).

    Selects photos that have never been classified, plus any classified by an
    older model version (so a model upgrade reclassifies stale rows without
    touching current ones). `reclassify_all=True` forces everything.

    Commits incrementally and exits cleanly if `shutdown_event` is set.
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")

        if reclassify_all:
            where = ""
            params: tuple = ()
        else:
            # NULL category = never classified; stale scene_model = model upgraded.
            where = "WHERE scene_category IS NULL OR scene_model IS NULL OR scene_model != ?"
            params = (SCENE_MODEL_TAG,)

        query = f"""
            SELECT p.id, p.path,
                   (SELECT COUNT(*) FROM faces f WHERE f.photo_id = p.id) AS n_faces
            FROM photos p
            {where}
        """
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        photos = conn.execute(query, params).fetchall()
        if not photos:
            print("[PixelRAG] No photos need scene classification.")
            return 0

        _ensure_model_loaded()

        total = len(photos)
        print(f"[PixelRAG] Classifying {total} photos "
              f"({CLIP_MODEL}/{CLIP_PRETRAINED}, batch={CLIP_BATCH}, device={_device})...")

        by_path = {p[1]: (p[0], p[2] or 0) for p in photos}
        all_paths = [p[1] for p in photos]

        classified = 0
        counts: Dict[str, int] = {}

        for start in range(0, total, CLIP_BATCH):
            if shutdown_event is not None and shutdown_event.is_set():
                conn.commit()
                print(f"[PixelRAG] Shutdown requested — committed {classified} photos")
                return classified

            batch_paths = all_paths[start:start + CLIP_BATCH]
            existing = [p for p in batch_paths if Path(p).exists()]
            if not existing:
                continue

            (probs, feats, dims), kept = _embed_batch(existing)
            if len(kept) == 0:
                continue

            recalls = _people_recall_scores(feats)

            for i, path in enumerate(kept):
                photo_id, n_faces = by_path[path]
                category, confidence, secondary, source = _route(
                    probs[i], n_faces, float(recalls[i])
                )

                order = np.argsort(probs[i])[::-1]
                top3 = json.dumps([
                    {"category": CATEGORIES[int(j)], "score": round(float(probs[i][int(j)]), 4)}
                    for j in order[:3]
                ])
                w, h = dims.get(path, (None, None))

                conn.execute(
                    """UPDATE photos
                       SET scene_category = ?, scene_confidence = ?, scene_tags = ?,
                           scene_low_confidence = ?, scene_secondary = ?,
                           scene_source = ?, scene_model = ?, width = ?, height = ?
                       WHERE id = ?""",
                    (category, confidence, top3,
                     1 if category == UNSORTED else 0, secondary,
                     source, SCENE_MODEL_TAG, w, h, photo_id),
                )
                conn.execute(
                    """INSERT OR REPLACE INTO photo_embeddings (photo_id, dim, embedding)
                       VALUES (?, ?, ?)""",
                    (photo_id, int(feats[i].shape[0]), feats[i].tobytes()),
                )
                counts[category] = counts.get(category, 0) + 1
                classified += 1

            conn.commit()

            done = min(start + CLIP_BATCH, total)
            if progress_callback:
                progress_callback(done, total, f"Classifying: {Path(batch_paths[-1]).name}")
            if done % (CLIP_BATCH * 20) < CLIP_BATCH:
                print(f"[PixelRAG]   Classified {done}/{total}...")

        conn.commit()
    finally:
        conn.close()

    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    print(f"[PixelRAG] Scene classification complete. {classified} photos.")
    print(f"[PixelRAG]   {summary}")
    return classified

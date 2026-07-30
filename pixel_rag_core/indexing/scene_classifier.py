# pixel_rag_core/indexing/scene_classifier.py
"""
CLIP-based scene classification for non-face photos.
Uses OpenCLIP ViT-B/32 with 'openai' pretrained weights.
Classifies photos into one of 12 categories using zero-shot classification.
Runs fully locally on CPU — no cloud dependencies.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Expanded Category taxonomy with prompt ensembling ────────────────────────
# Multiple prompts per category are averaged into one robust text embedding.
# This is the standard CLIP zero-shot technique from the original OpenAI paper.

CATEGORY_PROMPTS = {
    "landscape": [
        "a photo of a landscape, nature, mountains, or outdoors",
        "a scenic nature view with trees, fields, or sky",
        "an outdoor landscape photograph",
    ],
    "document": [
        "a photo of a document, receipt, text page, or paperwork",
        "a photograph of printed or handwritten text on paper",
        "a close-up photo of a document or form",
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
        "a screen capture showing a user interface or social media",
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

# Confidence threshold — flag as low confidence if below this
CONFIDENCE_THRESHOLD = 0.28  # Slightly lowered to trust model's top guess more.

# Module-level model cache
_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None
_text_features = None


def _ensure_model_loaded():
    """Lazy-load the CLIP model and pre-encode text prompts with ensembling."""
    global _clip_model, _clip_preprocess, _clip_tokenizer, _text_features

    if _clip_model is not None:
        return

    import open_clip
    import torch

    print("[PixelRAG] Loading OpenCLIP ViT-B/32 model...")
    model, _, preprocess = open_clip.create_model_and_transforms(
        'ViT-B-32', pretrained='openai'
    )
    tokenizer = open_clip.get_tokenizer('ViT-B-32')

    model.eval()

    # Prompt ensembling: encode all prompts per category, then average
    category_names = list(CATEGORY_PROMPTS.keys())
    ensemble_features = []

    with torch.no_grad():
        for cat in category_names:
            prompts = CATEGORY_PROMPTS[cat]
            tokens = tokenizer(prompts)
            feats = model.encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            # Average the prompt embeddings for this category
            avg_feat = feats.mean(dim=0)
            avg_feat = avg_feat / avg_feat.norm()
            ensemble_features.append(avg_feat)

    _clip_model = model
    _clip_preprocess = preprocess
    _clip_tokenizer = tokenizer
    _text_features = torch.stack(ensemble_features)

    print(f"[PixelRAG] CLIP model loaded. {len(category_names)} categories encoded "
          f"({sum(len(v) for v in CATEGORY_PROMPTS.values())} total prompts ensembled).")


def classify_scene(image_path: str) -> Tuple[str, float, str, bool, Optional[bytes]]:
    """
    Classify a single image into one of the scene categories and return its CLIP embedding.

    Returns:
        (category, confidence, top3_json, low_confidence, embedding_bytes)

    top3_json is a JSON string like:
        [{"category": "landscape", "score": 0.85}, ...]
    """
    import torch
    from PIL import Image, ImageOps

    _ensure_model_loaded()

    try:
        pil_img = Image.open(image_path)
        pil_img = ImageOps.exif_transpose(pil_img)
        if pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')

        img_tensor = _clip_preprocess(pil_img).unsqueeze(0)

        with torch.no_grad():
            image_features = _clip_model.encode_image(img_tensor)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            
            # Extract embedding bytes for semantic search
            emb_bytes = image_features.cpu().numpy().astype(np.float32).tobytes()

            # Compute similarities
            similarities = (image_features @ _text_features.T).squeeze(0)

            # Softmax for probabilities — temperature=15.0 for calibrated scores
            # (100.0 was far too aggressive, making all predictions appear 95%+ confident)
            probs = torch.softmax(similarities * 15.0, dim=0)

        category_names = list(CATEGORY_PROMPTS.keys())
        probs_np = probs.cpu().numpy()

        # Sort by score descending
        sorted_indices = np.argsort(probs_np)[::-1]

        top_category = category_names[sorted_indices[0]]
        top_confidence = float(probs_np[sorted_indices[0]])

        # Top 3 results
        top3 = []
        for idx in sorted_indices[:3]:
            top3.append({
                "category": category_names[idx],
                "score": round(float(probs_np[idx]), 4),
            })
        top3_json = json.dumps(top3)

        low_confidence = top_confidence < CONFIDENCE_THRESHOLD

        return top_category, top_confidence, top3_json, low_confidence, emb_bytes

    except Exception as e:
        print(f"[PixelRAG] CLIP classification error for {image_path}: {e}")
        return "object", 0.0, "[]", True, None



def classify_untagged_photos(
    db_path: str, 
    limit: Optional[int] = None, 
    reclassify_all: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    shutdown_event=None,
) -> int:
    """
    Classify photos using CLIP zero-shot classification.
    
    If reclassify_all=True, it will re-process all photos regardless of existing category.
    Photos where face_indexer already set scene_category='people' (high face coverage)
    have a non-NULL scene_category and are naturally skipped by the default query.
    
    If shutdown_event is set, commits partial progress and returns cleanly.
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")

        if reclassify_all:
            # Re-classify all photos
            query = "SELECT id, path FROM photos"
        else:
            # Classify photos that have never been tagged (regardless of face presence)
            # Photos with high face coverage already have scene_category='people' set by face_indexer
            query = """
                SELECT id, path FROM photos
                WHERE scene_category IS NULL
            """
            
        if limit is not None:
            query += f" LIMIT {limit}"

        photos = conn.execute(query).fetchall()

        if not photos:
            print("[PixelRAG] No photos to classify.")
            return 0

        print(f"[PixelRAG] Classifying {len(photos)} photos with CLIP...")

        classified = 0
        for i, (photo_id, path) in enumerate(photos):
            # Check shutdown event for clean early exit
            if shutdown_event is not None and shutdown_event.is_set():
                print(f"[PixelRAG] Shutdown requested — committing {classified} classified photos")
                conn.commit()
                return classified

            if not Path(path).exists():
                continue

            category, confidence, top3_json, low_conf, emb_bytes = classify_scene(path)

            conn.execute(
                """UPDATE photos
                   SET scene_category = ?,
                       scene_confidence = ?,
                       scene_tags = ?,
                       scene_low_confidence = ?
                   WHERE id = ?""",
                (category, confidence, top3_json, 1 if low_conf else 0, photo_id),
            )
            
            if emb_bytes:
                conn.execute(
                    """INSERT OR REPLACE INTO photo_embeddings (photo_id, dim, embedding)
                       VALUES (?, ?, ?)""",
                    (photo_id, 512, emb_bytes)
                )

            classified += 1

            if progress_callback and (i + 1) % 5 == 0:
                progress_callback(i + 1, len(photos), f"Classifying: {Path(path).name}")

            if (i + 1) % 20 == 0:
                conn.commit()
                print(f"[PixelRAG]   Classified {i + 1}/{len(photos)} photos...")

        conn.commit()
    finally:
        conn.close()

    print(f"[PixelRAG] Scene classification complete. {classified} photos classified.")
    return classified

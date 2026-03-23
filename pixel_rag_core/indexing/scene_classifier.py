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
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Category taxonomy with rich CLIP prompts ──────────────────────────────────
# Each prompt is carefully engineered for CLIP disambiguation.

CATEGORIES = {
    "landscape": "a photo of a landscape, nature, or outdoors",
    "document": "a photo of a document, receipt, or text page",
    "food": "a photo of food or a meal",
    "architecture": "a photo of a building, city, or architecture",
    "people": "a photo of a person, people, human body, or silhouette",
    "other": "a photo of something else, abstract, or unknown",
}

# Confidence threshold — below this, flag as low confidence
CONFIDENCE_THRESHOLD = 0.35

# Module-level model cache
_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None
_text_features = None


def _ensure_model_loaded():
    """Lazy-load the CLIP model and pre-encode text prompts."""
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

    # Pre-encode all category text prompts
    category_names = list(CATEGORIES.keys())
    prompts = [CATEGORIES[cat] for cat in category_names]

    with torch.no_grad():
        text_tokens = tokenizer(prompts)
        text_feats = model.encode_text(text_tokens)
        text_feats = text_feats / text_feats.norm(dim=-1, keepdim=True)

    _clip_model = model
    _clip_preprocess = preprocess
    _clip_tokenizer = tokenizer
    _text_features = text_feats

    print(f"[PixelRAG] CLIP model loaded. {len(category_names)} categories encoded.")


def classify_scene(image_path: str) -> Tuple[str, float, str, bool]:
    """
    Classify a single image into one of 12 scene categories.

    Returns:
        (category, confidence, top3_json, low_confidence)

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

            # Compute similarities
            similarities = (image_features @ _text_features.T).squeeze(0)

            # Softmax for probabilities
            probs = torch.softmax(similarities * 100.0, dim=0)  # temperature scaling

        category_names = list(CATEGORIES.keys())
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

        return top_category, top_confidence, top3_json, low_confidence

    except Exception as e:
        print(f"[PixelRAG] CLIP classification error for {image_path}: {e}")
        return "object", 0.0, "[]", True


def classify_untagged_photos(db_path: str, limit: Optional[int] = None) -> int:
    """
    Classify all photos that have no scene_category set and has_faces = 0.
    Photos with faces are already tagged as 'people' by the face indexer.

    Returns: number of photos classified.
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")

    query = """
        SELECT id, path FROM photos
        WHERE scene_category IS NULL
          AND (has_faces = 0 OR has_faces IS NULL)
    """
    if limit is not None:
        query += f" LIMIT {limit}"

    photos = conn.execute(query).fetchall()

    if not photos:
        print("[PixelRAG] No unclassified photos to process.")
        conn.close()
        return 0

    print(f"[PixelRAG] Classifying {len(photos)} photos with CLIP...")

    classified = 0
    for i, (photo_id, path) in enumerate(photos):
        if not Path(path).exists():
            continue

        category, confidence, top3_json, low_conf = classify_scene(path)

        conn.execute(
            """UPDATE photos
               SET scene_category = ?,
                   scene_confidence = ?,
                   scene_tags = ?,
                   scene_low_confidence = ?
               WHERE id = ?""",
            (category, confidence, top3_json, 1 if low_conf else 0, photo_id),
        )
        classified += 1

        if (i + 1) % 20 == 0:
            conn.commit()
            print(f"[PixelRAG]   Classified {i + 1}/{len(photos)} photos...")

    conn.commit()
    conn.close()
    print(f"[PixelRAG] Scene classification complete. {classified} photos classified.")
    return classified

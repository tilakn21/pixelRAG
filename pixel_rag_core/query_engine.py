# pixel_rag_core/query_engine.py

import sqlite3
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

from groq import Groq

# Add project root to path so we can resolve pixel_rag_core imports easily
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pixel_rag_core.config import DB_PATH

# Valid scene categories for the intent parser
VALID_SCENE_CATEGORIES = [
    "landscape", "document", "food", "architecture", "animal",
    "vehicle", "screenshot", "art", "event", "night",
    "object", "map_chart", "people",
]


# Models this API key can actually use, best first. The previous default
# (meta-llama/llama-4-scout-17b-16e-instruct) was decommissioned and returned
# 404 on every search — silently, so search appeared to "work" while returning
# the entire library. Measured on real queries against this taxonomy:
#     openai/gpt-oss-120b  6/7 correct, 1.45 s   <- default (got names right)
#     openai/gpt-oss-20b   6/7 correct, 0.75 s   (missed an unusual first name)
#     allam-2-7b           6/7 correct, 0.12 s   (fast fallback)
#     groq/compound        1/7 — does not reliably emit JSON, do not use
# Re-probe with scratch/probe_groq_models.py if Groq rotates its lineup again.
GROQ_MODEL_CHAIN = [
    os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    "openai/gpt-oss-20b",
    "allam-2-7b",
]


class GraphQueryEngine:
    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = Path(db_path)
        self.groq_model = GROQ_MODEL_CHAIN[0]
        # de-duplicated, order preserved
        self.model_chain = list(dict.fromkeys(GROQ_MODEL_CHAIN))
        
        # Initialize Groq
        try:
            groq_key = os.getenv("GROQ_API_KEY")
            if groq_key:
                self.groq_client = Groq(api_key=groq_key)
            else:
                self.groq_client = None
                print("[PixelRAG] Warning: GROQ_API_KEY not found in environment. Natural language parsing will not work.")
        except Exception as e:
            self.groq_client = None
            print(f"[PixelRAG] Warning: Groq Client failed to initialize ({e}).")

    def _resolve_names(self, names: List[str]) -> tuple[List[str], Optional[str]]:
        """
        Resolve user-typed names against confirmed person names in the DB
        using fuzzy matching (rapidfuzz token_sort_ratio).

        Returns: (resolved_names, error_message_or_none)
        """
        if not names:
            return [], None

        try:
            from rapidfuzz import fuzz

            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            db_names = [
                row[0] for row in
                conn.execute("SELECT name FROM people WHERE confirmed = 1 OR name NOT LIKE 'Cluster_%'").fetchall()
            ]
            conn.close()

            if not db_names:
                return names, None  # No confirmed names in DB, pass through

            resolved = []
            for query_name in names:
                best_match = None
                best_score = 0
                for db_name in db_names:
                    score = fuzz.token_sort_ratio(query_name.lower(), db_name.lower())
                    if score > best_score:
                        best_score = score
                        best_match = db_name

                if best_score >= 75:
                    resolved.append(best_match)
                    if best_match.lower() != query_name.lower():
                        print(f"[PixelRAG] Fuzzy match: '{query_name}' → '{best_match}' (score: {best_score})")
                else:
                    # No good match found
                    suggestions = sorted(
                        [(name, fuzz.token_sort_ratio(query_name.lower(), name.lower())) for name in db_names],
                        key=lambda x: x[1], reverse=True
                    )[:3]
                    suggest_str = ", ".join([f"'{s[0]}'" for s in suggestions if s[1] > 40])
                    msg = f"No person named '{query_name}' found."
                    if suggest_str:
                        msg += f" Did you mean: {suggest_str}?"
                    return [], msg

            return resolved, None

        except ImportError:
            print("[PixelRAG] rapidfuzz not installed, using exact name matching.")
            return names, None

    def parse_query(self, prompt: str) -> Dict[str, Any]:
        """Uses Gemini to parse a natural language prompt into structured search parameters."""
        categories_str = ", ".join([f"'{c}'" for c in VALID_SCENE_CATEGORIES])

        system_instruction = f'''
        You are a natural language to search parameter converter for a photo library database.
        Extract the search parameters from the user's prompt.
        Return a JSON object with EXACTLY the following keys:
        - names: A list of strings containing people's names. Empty list if none.
        - date: A string representing a date, year '2023', month '2023-10', or empty string if none. Choose the simplest substring out of YYYY-MM-DD.
        - location: A string representing a city, state, or country. Empty string if none.
        - scene_category: One of the following valid categories ONLY: {categories_str}. Set to null if the user does not mention a photo type. "people" is for photos of people/faces.
        - semantic_query: A string representing visual elements, objects, clothing, or actions described by the user (e.g., "red color cloth", "sitting on a car", "wearing sunglasses"). Empty string if none. Do NOT include people's names in this string.
        - strict: Boolean. True if the query implies ALL people must be in the photo (e.g., "tilak and alice put together", "photos of tilak and alice"). False if ANY ("tilak or alice"). Default to True for a single person or if ambiguous.
        - exclusive: Boolean. True if the user explicitly mentions "only", "just", "alone", "nobody else", or "by himself/herself". Default to False.

        IMPORTANT RULES:
        - For scene_category, use ONLY the exact category names listed above. Do NOT invent new categories.
        - "photos of animals" -> scene_category: "animal"
        - "landscape photos" -> scene_category: "landscape"
        - "receipts" or "bills" or "documents" -> scene_category: "document"
        - "screenshots" -> scene_category: "screenshot"
        - "night photos" or "night sky" -> scene_category: "night"
        - "food photos" or "meals" -> scene_category: "food"
        - "photos of buildings" -> scene_category: "architecture"
        - If the user mentions a person by name, do NOT set scene_category to "people" — the names field handles that.
        - scene_category should be null when the user does not mention any content type.
        '''

        # `parse_ok` distinguishes "the user asked for everything" from "we could
        # not understand the query". Without it, a failed parse produced an empty
        # intent, which built `SELECT p.* FROM photos` with no WHERE clause and
        # returned all 28,512 photos as if they were search results.
        def _empty(reason: str):
            return {"names": [], "date": "", "location": "", "scene_category": None,
                    "semantic_query": "", "strict": True, "exclusive": False,
                    "parse_ok": False, "parse_error": reason}

        if not self.groq_client:
            print("[PixelRAG] No Groq client (GROQ_API_KEY missing). Cannot parse query.")
            return _empty("Search needs GROQ_API_KEY to understand your query.")

        last_err = None
        for model in self.model_chain:
            print(f"[PixelRAG] Querying Groq ({model}) to parse intent...")
            try:
                completion = self.groq_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": f"Extract parameters from this query: {prompt}"}
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"}
                )
                data = json.loads(completion.choices[0].message.content)
                if model != self.groq_model:
                    print(f"[PixelRAG] Fell back to {model} for intent parsing.")
                params = self._finalize_params(data)
                params["parse_ok"] = True
                return params
            except Exception as e:
                last_err = e
                print(f"[PixelRAG] Groq parse failed on {model}: {str(e)[:160]}")

        return _empty(f"Could not parse the query ({str(last_err)[:120]})")

    def _finalize_params(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize parsed JSON into standard search parameters."""
        cat = data.get("scene_category")
        # The model occasionally invents a category. Anything outside the known
        # taxonomy is dropped rather than passed into SQL, where it would match
        # nothing and look like "search is broken".
        if cat is not None and cat not in VALID_SCENE_CATEGORIES:
            print(f"[PixelRAG] Ignoring unknown scene_category from model: {cat!r}")
            cat = None
        return {
            "names": data.get("names", []) or [],
            "date": data.get("date", "") or "",
            "location": data.get("location", "") or "",
            "scene_category": cat,
            "semantic_query": data.get("semantic_query", "") or "",
            "strict": data.get("strict", True),
            "exclusive": data.get("exclusive", False)
        }

    def build_sql(self, names: List[str], date: str, location: str,
                  scene_category: Optional[str] = None,
                  strict: bool = True, exclusive: bool = False,
                  # Keep backward compat with old 'category' param
                  category: str = "") -> Dict[str, Any]:
        """Builds a SQL query deterministically from extracted parameters."""

        base_query = "SELECT p.* FROM photos p"
        where_clauses = []
        params = []

        # Location filtering
        if location:
            where_clauses.append("(p.city LIKE ? OR p.state LIKE ? OR p.country LIKE ?)")
            loc_param = f"%{location}%"
            params.extend([loc_param, loc_param, loc_param])

        # Date filtering (simple text match)
        if date:
            where_clauses.append("p.created_at LIKE ?")
            params.append(f"%{date}%")

        # Scene category filtering (new CLIP-based categories)
        if scene_category and scene_category in VALID_SCENE_CATEGORIES:
            where_clauses.append("p.scene_category = ?")
            params.append(scene_category)
        elif category:
            # Legacy category fallback
            where_clauses.append("p.category LIKE ?")
            params.append(f"%{category}%")

        # People filtering
        if names:
            if strict:
                # Must contain ALL specified people
                for name in names:
                    where_clauses.append(f"""
                        p.id IN (
                            SELECT photo_id FROM faces f 
                            JOIN people ppl ON f.person_id = ppl.id 
                            WHERE ppl.name LIKE ? COLLATE NOCASE
                        )
                    """)
                    params.append(f"%{name.strip()}%")
            else:
                # Contains ANY of the specified people
                or_clauses = []
                for name in names:
                    or_clauses.append("ppl.name LIKE ? COLLATE NOCASE")
                    params.append(f"%{name.strip()}%")

                or_stmt = " OR ".join(or_clauses)
                where_clauses.append(f"""
                    p.id IN (
                        SELECT photo_id FROM faces f 
                        JOIN people ppl ON f.person_id = ppl.id 
                        WHERE ({or_stmt})
                    )
                """)

            # Exclusivity check: absolute purity (no other face present, named or unnamed)
            if exclusive:
                # Build exclusion: exclude photos that have ANY face that is either:
                # 1) unassigned/unconfirmed (ppl2.id IS NULL or cluster)
                # 2) a confirmed person who is NOT in the requested names list
                name_exclusions = []
                for name in names:
                    name_exclusions.append("ppl2.name LIKE ? COLLATE NOCASE")
                    params.append(f"%{name.strip()}%")

                exclusion_or = " OR ".join(name_exclusions)
                where_clauses.append(f"""
                    p.id NOT IN (
                        SELECT f2.photo_id FROM faces f2
                        LEFT JOIN people ppl2 ON f2.person_id = ppl2.id
                        WHERE ppl2.id IS NULL 
                           OR ppl2.name LIKE 'Cluster_%'
                           OR NOT ({exclusion_or})
                    )
                """)

        query = base_query
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        explanation = f"Searching for: Names={names}, Date='{date}', Location='{location}', SceneCategory='{scene_category}', Strict={strict}, Exclusive={exclusive}"
        return {"sql": query, "params": params, "explanation": explanation}

    def execute_query(self, sql: str, params: List[Any]) -> List[Dict[str, Any]]:
        """Executes the raw SQL query to fetch photo records."""
        if not sql:
            return []

        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.close()

            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"[PixelRAG] SQLite Execution Error: {e}\nQuery was: {sql}\nParams: {params}")
            return []

    def run_prompt(self, prompt: str) -> Dict[str, Any]:
        """End-to-end pipeline: Parse Prompt -> Build SQL -> Fetch -> Return."""
        print(f"\n--- Natural Language Query ---")
        print(f"Prompt: '{prompt}'")

        # 1. Parse Prompt into structured JSON
        parsed = self.parse_query(prompt)
        print(f"LLM Extracted Params: {json.dumps(parsed, indent=2)}")

        # Refuse to answer a query we could not understand. Returning the whole
        # library instead of an error is what made search look silently broken.
        if not parsed.get("parse_ok", True):
            return {
                "prompt": prompt, "parsed": parsed, "sql": "", "params": [],
                "photos": [], "intent": parsed,
                "error": parsed.get("parse_error", "Could not understand that query."),
            }

        # A parse that yields no constraint at all would also select everything.
        # Treat that as "no results" rather than "all results".
        if not any([parsed.get("names"), parsed.get("date"), parsed.get("location"),
                    parsed.get("scene_category"), parsed.get("semantic_query")]):
            return {
                "prompt": prompt, "parsed": parsed, "sql": "", "params": [],
                "photos": [], "intent": parsed,
                "error": ("No searchable filter found in that query. Try a person's "
                          "name, a place, a year, or a category like documents, "
                          "screenshots or food."),
            }

        # 2. Fuzzy name resolution
        names = parsed.get("names", [])
        error_msg = None
        if names:
            names, error_msg = self._resolve_names(names)
            if error_msg:
                print(f"[PixelRAG] Name resolution error: {error_msg}")
                return {
                    "prompt": prompt,
                    "parsed": parsed,
                    "sql": "",
                    "params": [],
                    "paths": [],
                    "error": error_msg,
                }

        # 3. Build SQL
        built = self.build_sql(
            names=names,
            date=parsed.get("date", ""),
            location=parsed.get("location", ""),
            scene_category=parsed.get("scene_category"),
            strict=parsed.get("strict", True),
            exclusive=parsed.get("exclusive", False)
        )
        sql = built["sql"]
        params = built["params"]
        explanation = built["explanation"]

        print(f"Generated SQL: {sql}\nParams: {params}\n")

        # 4. Execute SQL
        photos = self.execute_query(sql, params)
        print(f"Found {len(photos)} matching photos via SQL.")

        # 5. Semantic Search (CLIP) if semantic_query exists
        semantic_query = parsed.get("semantic_query", "").strip()
        if semantic_query and photos:
            print(f"Applying semantic search for: '{semantic_query}'")
            import torch
            import numpy as np
            import pixel_rag_core.indexing.scene_classifier as sc
            
            try:
                sc._ensure_model_loaded()
                with torch.no_grad():
                    text_tokens = sc._clip_tokenizer([semantic_query])
                    text_features = sc._clip_model.encode_text(text_tokens)
                    text_features /= text_features.norm(dim=-1, keepdim=True)
                    text_emb = text_features.cpu().numpy().astype(np.float32).flatten()

                # Get embeddings for candidate photos
                conn = sqlite3.connect(self.db_path)
                photo_ids = [p["id"] for p in photos]
                placeholders = ",".join(["?"] * len(photo_ids))
                emb_rows = conn.execute(
                    f"SELECT photo_id, embedding FROM photo_embeddings WHERE photo_id IN ({placeholders})", 
                    photo_ids
                ).fetchall()
                conn.close()

                emb_dict = {}
                for pid, emb_bytes in emb_rows:
                    emb_dict[pid] = np.frombuffer(emb_bytes, dtype=np.float32)

                # Score photos
                scored_photos = []
                for p in photos:
                    pid = p["id"]
                    if pid in emb_dict:
                        sim = float(np.dot(text_emb, emb_dict[pid]))
                        p["semantic_score"] = sim
                        scored_photos.append(p)
                
                # Sort by similarity
                scored_photos.sort(key=lambda x: x["semantic_score"], reverse=True)
                
                # Filter out low relevance (heuristic threshold, e.g., 0.2)
                photos = [p for p in scored_photos if p["semantic_score"] > 0.2]
                print(f"Semantic filtering kept {len(photos)} photos.")
            except Exception as e:
                print(f"[PixelRAG] Semantic search failed: {e}")

        return {
            "prompt": prompt,
            "intent": parsed,
            "sql": sql,
            "params": params,
            "photos": photos
        }


def search(db_path: str, query: str) -> Dict[str, Any]:
    """Top-level search entry point for the FastAPI server."""
    engine = GraphQueryEngine(db_path=db_path)
    return engine.run_prompt(query)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Query the photo Graph RAG system using natural language.")
    parser.add_argument("prompt", type=str, nargs="*", help="Natural language query (e.g. 'Photos of Tilak and Alice in London in 2022')")
    args = parser.parse_args()

    prompt = " ".join(args.prompt)
    if not prompt:
        print("Please provide a prompt. Example: python query_engine.py \"Show me photos of Shriyash from 2023\"")
        sys.exit(1)

    if not os.getenv("GROQ_API_KEY"):
        print("ERROR: GROQ_API_KEY environment variable is missing. It is required for parsing natural language.")
        sys.exit(1)

    engine = GraphQueryEngine()
    results = engine.run_prompt(prompt)

    if results.get("error"):
        print(f"\n⚠️ {results['error']}")
    elif results.get("photos"):
        print("\nResult Photos:")
        for p in results["photos"][:10]:  # Print top 10
            print(f" - {p['path']}")
        if len(results["photos"]) > 10:
            print(f" ... and {len(results['photos']) - 10} more.")

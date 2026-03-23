# pixel_rag_core/query_engine.py

import sqlite3
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types

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


class GraphQueryEngine:
    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = Path(db_path)
        self.model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")  # Free tier defaults
        try:
            self.client = genai.Client()  # Requires GEMINI_API_KEY
        except Exception as e:
            self.client = None
            print(f"[PixelRAG] Warning: LLM Client failed to initialize ({e}). NLP will not work.")

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
        - strict: Boolean. True if the query implies ALL people must be in the photo (e.g., "tilak and alice put together", "photos of tilak and alice"). False if ANY ("tilak or alice"). Default to True for a single person or if ambiguous.
        - exclusive: Boolean. True if the user explicitly mentions "only", "just", "nobody else", or "exclusively these people". Default to False.

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

        if not self.client:
            print("[PixelRAG] No Gemini Client found. Cannot parse query.")
            return {"names": [], "date": "", "location": "", "scene_category": None, "strict": True, "exclusive": False}

        print(f"[PixelRAG] Querying {self.model_name} (Zero-cost free tier) to parse intent...")
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=f"Extract parameters from this query: {prompt}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text.strip())
            return {
                "names": data.get("names", []),
                "date": data.get("date", ""),
                "location": data.get("location", ""),
                "scene_category": data.get("scene_category"),
                "strict": data.get("strict", True),
                "exclusive": data.get("exclusive", False)
            }
        except Exception as e:
            print(f"[PixelRAG] Failed to parse query via LLM: {e}")
            return {"names": [], "date": "", "location": "", "scene_category": None, "strict": True, "exclusive": False}

    def build_sql(self, names: List[str], date: str, location: str,
                  scene_category: Optional[str] = None,
                  strict: bool = True, exclusive: bool = False,
                  # Keep backward compat with old 'category' param
                  category: str = "") -> Dict[str, Any]:
        """Builds a SQL query deterministically from extracted parameters."""

        base_query = "SELECT p.path FROM photos p"
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

            # Exclusivity check: no other CONFIRMED named person present
            if exclusive:
                # Build exclusion: exclude photos that have a confirmed named person
                # who is NOT in the requested names list
                name_exclusions = []
                for name in names:
                    name_exclusions.append("ppl2.name LIKE ? COLLATE NOCASE")
                    params.append(f"%{name.strip()}%")

                exclusion_or = " OR ".join(name_exclusions)
                where_clauses.append(f"""
                    p.id NOT IN (
                        SELECT f2.photo_id FROM faces f2
                        JOIN people ppl2 ON f2.person_id = ppl2.id
                        WHERE ppl2.name NOT LIKE 'Cluster_%'
                          AND ppl2.name != 'Unknown'
                          AND NOT ({exclusion_or})
                    )
                """)

        query = base_query
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        explanation = f"Searching for: Names={names}, Date='{date}', Location='{location}', SceneCategory='{scene_category}', Strict={strict}, Exclusive={exclusive}"
        return {"sql": query, "params": params, "explanation": explanation}

    def execute_query(self, sql: str, params: List[Any]) -> List[str]:
        """Executes the raw SQL query to fetch photo paths."""
        if not sql:
            return []

        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.close()

            return [row[0] for row in rows]
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

        # 4. Execute
        paths = self.execute_query(sql, params)
        print(f"Found {len(paths)} matching photos.")

        return {
            "prompt": prompt,
            "parsed": parsed,
            "sql": sql,
            "params": params,
            "paths": paths
        }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Query the photo Graph RAG system using natural language.")
    parser.add_argument("prompt", type=str, nargs="*", help="Natural language query (e.g. 'Photos of Tilak and Alice in London in 2022')")
    args = parser.parse_args()

    prompt = " ".join(args.prompt)
    if not prompt:
        print("Please provide a prompt. Example: python query_engine.py \"Show me photos of Shriyash from 2023\"")
        sys.exit(1)

    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY environment variable is missing. It is required for parsing natural language.")
        sys.exit(1)

    engine = GraphQueryEngine()
    results = engine.run_prompt(prompt)

    if results.get("error"):
        print(f"\n⚠️ {results['error']}")
    elif results.get("paths"):
        print("\nResult Paths:")
        for p in results["paths"][:10]:  # Print top 10
            print(f" - {p}")
        if len(results["paths"]) > 10:
            print(f" ... and {len(results['paths']) - 10} more.")

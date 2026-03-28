# PixelRAG

**Local-first AI photo intelligence.** PixelRAG uses on-device AI to automatically detect faces, classify scenes, and enable natural language search across your personal photo library — without uploading anything to the cloud.

## Architecture

```
pixelRAG/
├── pixel_rag_core/      # AI engine (InsightFace, CLIP, Gemini, HDBSCAN)
├── pixel_rag_server/    # FastAPI backend (REST API)
└── pixel_rag_web/       # Next.js frontend (React)
```

## Quick Start

### 1. Configure the backend

Create a `.env` file inside `pixel_rag_server/`:

```bash
LIBRARY_PATH="/path/to/your/photo/folder"
```

### 2. Install dependencies

**Backend:**
```bash
pip install -r pixel_rag_server/requirements.txt
```

**Frontend:**
```bash
cd pixel_rag_web && npm install && cd ..
```

### 3. Start both servers

**Terminal 1 — FastAPI backend (port 8000):**
```bash
uvicorn pixel_rag_server.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Next.js frontend (port 3000):**
```bash
cd pixel_rag_web && npm run dev
```

### 4. Open in browser

- **Desktop:** [http://localhost:3000](http://localhost:3000)
- **Phone (same WiFi):** Replace `localhost` with your Mac's IP address:
  ```bash
  ifconfig | grep "inet " | grep -v 127.0.0.1
  ```
  Then open `http://<YOUR_IP>:3000` on your phone. Also set the API URL:
  ```bash
  # In pixel_rag_web/.env.local
  NEXT_PUBLIC_API_URL=http://<YOUR_IP>:8000
  ```

## Features

- 📸 **Smart Gallery** — Infinite scroll masonry grid with WebP thumbnails
- 🔍 **Natural Language Search** — "Show me photos of Tilak in Mumbai"
- 👤 **Face Recognition** — Automatic identity grouping with HDBSCAN
- 🏷️ **Scene Classification** — AI-powered category tagging (Landscape, Food, etc.)
- 📍 **Location Data** — Reverse geocoding from EXIF GPS coordinates
- 🌙 **Premium Dark UI** — Glassmorphism aesthetic, fully responsive

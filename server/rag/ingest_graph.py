"""
Overnight pipeline — Parth Concept Knowledge Graph Builder
==========================================================
Phase 1 : Seed NCERT concept nodes + prerequisite edges → Postgres   (~2s)
Phase 2 : Search YouTube for Khan Academy videos per concept          (~3 min)
Phase 3 : Download transcripts (youtube-transcript-api)               (~5 min)
Phase 4 : Chunk + embed → ChromaDB 'ka_transcripts' collection        (~20 min)
Phase 5 : Print summary

Resume-safe: re-run any time — skips already-processed videos.

Usage:
    cd /Volumes/Seagate/Parth/server
    source venv/bin/activate
    python rag/ingest_graph.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import asyncpg
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
from tqdm import tqdm
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
import yt_dlp

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import Config

PG_DSN        = "postgresql://parth:parth_dev@localhost:5432/parth"
PROGRESS_FILE = Config.DATA_DIR / "graph_ingest_progress.json"
GRAPH_JSON    = Config.DATA_DIR / "concept_graph.json"   # fallback when Postgres is down
KA_CHANNEL_ID = "UCtXYEpX0C5w8aDe5Z-0Ko_A"   # Khan Academy official YouTube channel
CHUNK_WORDS   = 150    # words per ChromaDB chunk
VIDEOS_PER_CONCEPT = 6
SEARCH_DELAY  = 3.0    # seconds between YouTube searches
TRANSCRIPT_DELAY = 1.5  # seconds between transcript fetches

# ── NCERT concept graph definition ─────────────────────────────────────────

NCERT_CONCEPTS = [
    # Mathematics
    {"id": "arithmetic",         "label": "Arithmetic — Numbers & Operations", "subject": "mathematics", "grade_min": 1, "grade_max": 5,  "description": "Addition, subtraction, multiplication, division and number sense"},
    {"id": "fractions",          "label": "Fractions",                          "subject": "mathematics", "grade_min": 3, "grade_max": 6,  "description": "Parts of a whole: numerator, denominator, equivalent fractions, operations"},
    {"id": "decimals",           "label": "Decimals",                           "subject": "mathematics", "grade_min": 4, "grade_max": 7,  "description": "Base-10 fractions, place value, decimal operations"},
    {"id": "bodmas",             "label": "Order of Operations (BODMAS)",       "subject": "mathematics", "grade_min": 5, "grade_max": 7,  "description": "Brackets, Orders, Division, Multiplication, Addition, Subtraction"},
    {"id": "ratios",             "label": "Ratios & Proportions",               "subject": "mathematics", "grade_min": 6, "grade_max": 8,  "description": "Comparing quantities, direct and inverse proportion, percentages"},
    {"id": "geometry",           "label": "Geometry — Shapes & Measurement",   "subject": "mathematics", "grade_min": 4, "grade_max": 10, "description": "Angles, triangles, circles, area, perimeter, Pythagoras theorem"},
    {"id": "algebra_basics",     "label": "Algebra — Variables & Equations",   "subject": "mathematics", "grade_min": 6, "grade_max": 9,  "description": "Linear equations, variables, expressions, simple inequalities"},
    # Science — Biology
    {"id": "cell_biology",       "label": "Cell Structure & Function",          "subject": "science",     "grade_min": 8, "grade_max": 10, "description": "Cell theory, organelles, prokaryotes vs eukaryotes, cell division"},
    {"id": "photosynthesis",     "label": "Photosynthesis",                     "subject": "science",     "grade_min": 7, "grade_max": 10, "description": "How plants convert sunlight to food using chlorophyll and CO₂"},
    {"id": "human_body",         "label": "Human Body Systems",                 "subject": "science",     "grade_min": 5, "grade_max": 10, "description": "Digestive, circulatory, respiratory, skeletal and nervous systems"},
    {"id": "ecosystem",          "label": "Ecosystems & Food Chains",           "subject": "science",     "grade_min": 6, "grade_max": 10, "description": "Producers, consumers, decomposers, energy flow, biodiversity"},
    {"id": "water_cycle",        "label": "Water Cycle",                        "subject": "science",     "grade_min": 5, "grade_max": 7,  "description": "Evaporation, condensation, precipitation, transpiration"},
    # Science — Physics
    {"id": "newton_laws",        "label": "Newton's Laws of Motion",            "subject": "science",     "grade_min": 9, "grade_max": 10, "description": "Inertia, F=ma, action-reaction, gravity and acceleration"},
    {"id": "electricity",        "label": "Electricity & Circuits",             "subject": "science",     "grade_min": 7, "grade_max": 10, "description": "Current, voltage, resistance, Ohm's law, series and parallel circuits"},
    {"id": "magnetism",          "label": "Magnetism & Electromagnetism",       "subject": "science",     "grade_min": 6, "grade_max": 10, "description": "Magnetic fields, poles, electromagnets, motors and generators"},
    {"id": "light_optics",       "label": "Light & Optics",                    "subject": "science",     "grade_min": 8, "grade_max": 10, "description": "Reflection, refraction, lenses, mirrors, the electromagnetic spectrum"},
    {"id": "sound",              "label": "Sound & Waves",                      "subject": "science",     "grade_min": 9, "grade_max": 10, "description": "Vibration, frequency, amplitude, pitch, speed of sound, echo"},
    # Science — Chemistry
    {"id": "periodic_table",     "label": "Periodic Table & Elements",          "subject": "science",     "grade_min": 9, "grade_max": 10, "description": "Atomic structure, periods and groups, metals and non-metals, bonding"},
    # History
    {"id": "mughal_empire",      "label": "Mughal Empire",                      "subject": "history",     "grade_min": 7, "grade_max": 8,  "description": "Babur to Aurangzeb: administration, culture, architecture, decline"},
    {"id": "indian_independence","label": "Indian Independence Movement",       "subject": "history",     "grade_min": 8, "grade_max": 10, "description": "1857 revolt to 1947: Gandhi, non-cooperation, partition, constitution"},
]

NCERT_EDGES = [
    # Mathematics progression (prerequisite)
    ("arithmetic",     "fractions",      "prerequisite"),
    ("arithmetic",     "geometry",       "prerequisite"),
    ("arithmetic",     "bodmas",         "prerequisite"),
    ("fractions",      "decimals",       "prerequisite"),
    ("fractions",      "bodmas",         "co-requisite"),
    ("fractions",      "ratios",         "prerequisite"),
    ("decimals",       "ratios",         "co-requisite"),
    ("ratios",         "algebra_basics", "prerequisite"),
    ("arithmetic",     "algebra_basics", "prerequisite"),
    # Mathematics leads-to chain
    ("arithmetic",     "fractions",      "leads-to"),
    ("fractions",      "decimals",       "leads-to"),
    ("decimals",       "ratios",         "leads-to"),
    ("ratios",         "algebra_basics", "leads-to"),
    ("geometry",       "algebra_basics", "co-requisite"),
    # Physics dependencies
    ("arithmetic",     "newton_laws",    "prerequisite"),
    ("geometry",       "newton_laws",    "co-requisite"),
    ("newton_laws",    "electricity",    "prerequisite"),
    ("newton_laws",    "light_optics",   "prerequisite"),
    ("newton_laws",    "sound",          "prerequisite"),
    ("electricity",    "magnetism",      "leads-to"),
    ("electricity",    "magnetism",      "co-requisite"),
    ("geometry",       "light_optics",   "co-requisite"),
    # Biology chain
    ("cell_biology",   "photosynthesis", "prerequisite"),
    ("cell_biology",   "human_body",     "prerequisite"),
    ("cell_biology",   "photosynthesis", "leads-to"),
    ("photosynthesis", "ecosystem",      "prerequisite"),
    ("photosynthesis", "ecosystem",      "leads-to"),
    ("water_cycle",    "ecosystem",      "co-requisite"),
    # Chemistry
    ("periodic_table", "electricity",    "co-requisite"),
    # History
    ("mughal_empire",  "indian_independence", "leads-to"),
]

# ── Khan Academy search queries per concept ─────────────────────────────────

KA_QUERIES = {
    "arithmetic":          "arithmetic basic operations numbers",
    "fractions":           "fractions introduction numerator denominator",
    "decimals":            "decimals introduction place value",
    "bodmas":              "order of operations PEMDAS BODMAS",
    "ratios":              "ratios and proportions introduction",
    "geometry":            "basic geometry angles triangles area",
    "algebra_basics":      "introduction to algebra variables equations",
    "cell_biology":        "cell structure function biology",
    "photosynthesis":      "photosynthesis how plants make food",
    "human_body":          "human body systems overview",
    "ecosystem":           "ecosystems food chains energy",
    "water_cycle":         "water cycle evaporation condensation",
    "newton_laws":         "Newton's laws of motion force",
    "electricity":         "electricity circuits current voltage",
    "magnetism":           "magnetism magnetic fields electromagnetism",
    "light_optics":        "light reflection refraction optics",
    "sound":               "sound waves frequency pitch",
    "periodic_table":      "periodic table elements atoms",
    "mughal_empire":       "Mughal empire history India Akbar",
    "indian_independence": "Indian independence movement Gandhi",
}


# ── Progress helpers ─────────────────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text())
        except Exception:
            pass
    return {"videos_done": {}, "failed_videos": []}


def save_progress(progress: dict):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


# ── Phase 0: Always save graph to JSON (Postgres-independent) ───────────────

def save_graph_json(progress: dict):
    """Write concept graph + embedded video IDs to a JSON file the API can read."""
    nodes = []
    for c in NCERT_CONCEPTS:
        vid_ids = list(set(progress["videos_done"].get(c["id"], [])))
        nodes.append({**c, "video_ids": vid_ids, "video_count": len(vid_ids)})
    edges = [{"source": f, "target": t, "type": tp} for f, t, tp in NCERT_EDGES]
    GRAPH_JSON.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_JSON.write_text(json.dumps({"nodes": nodes, "edges": edges}, indent=2))


# ── Phase 1: Postgres concept graph ─────────────────────────────────────────

async def seed_postgres(conn: asyncpg.Connection):
    print("\n── Phase 1: Seeding concept graph in Postgres ──────────────────")

    # Ensure ka_videos table exists (in case schema was applied before this addition)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_graph.ka_videos (
            video_id         TEXT NOT NULL,
            concept_id       TEXT NOT NULL,
            title            TEXT DEFAULT '',
            transcript_chars INT DEFAULT 0,
            embedded         BOOLEAN DEFAULT false,
            fetched_at       TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (video_id, concept_id)
        )
    """)
    await conn.execute("""
        ALTER TABLE curriculum_graph.concepts
        ADD COLUMN IF NOT EXISTS video_ids TEXT[] DEFAULT '{}'
    """)

    for c in NCERT_CONCEPTS:
        await conn.execute("""
            INSERT INTO curriculum_graph.concepts
                (id, label, subject, grade_min, grade_max, description)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (id) DO UPDATE
            SET label=$2, subject=$3, grade_min=$4, grade_max=$5, description=$6
        """, c["id"], c["label"], c["subject"], c["grade_min"], c["grade_max"], c["description"])

    for from_id, to_id, edge_type in NCERT_EDGES:
        await conn.execute("""
            INSERT INTO curriculum_graph.concept_edges (from_id, to_id, type)
            VALUES ($1,$2,$3)
            ON CONFLICT (from_id, to_id, type) DO NOTHING
        """, from_id, to_id, edge_type)

    print(f"  ✓ {len(NCERT_CONCEPTS)} concepts, {len(NCERT_EDGES)} edges seeded")


# ── Phase 2: YouTube search ──────────────────────────────────────────────────

def search_ka_videos(concept_id: str, query: str) -> list[dict]:
    """Return up to VIDEOS_PER_CONCEPT Khan Academy video dicts {id, title}.

    Uses ytsearch with "Khan Academy" in the query. The query specificity is
    sufficient — no additional channel/title filtering needed.
    """
    search_term = f"Khan Academy {query}"
    ydl_opts = {
        "quiet":        True,
        "no_warnings":  True,
        "extract_flat": True,
        "ignoreerrors": True,
    }
    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"ytsearch{VIDEOS_PER_CONCEPT * 2}:{search_term}",
                download=False,
            )
            if not info or "entries" not in info:
                return []
            for entry in (info["entries"] or []):
                if not entry or not entry.get("id"):
                    continue
                duration = entry.get("duration") or 999
                if duration < 1500:  # skip very long videos (> 25 min)
                    results.append({"id": entry["id"], "title": entry.get("title", "")})
                if len(results) >= VIDEOS_PER_CONCEPT:
                    break
    except Exception as e:
        print(f"    ⚠ search error for {concept_id}: {e}")
    return results


# ── Phase 3: Transcript download ─────────────────────────────────────────────

def get_transcript(video_id: str) -> str:
    """Download transcript text for a YouTube video. Returns '' on failure."""
    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(s["text"] for s in segments)
    except (NoTranscriptFound, TranscriptsDisabled):
        # Try auto-generated
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            t = transcript_list.find_generated_transcript(["en", "en-US"])
            segments = t.fetch()
            return " ".join(s["text"] for s in segments)
        except Exception:
            return ""
    except Exception:
        return ""


# ── Phase 4: ChromaDB embedding ──────────────────────────────────────────────

def get_ka_collection():
    chroma_path = Config.DATA_DIR / "chroma"
    chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_path))
    embed_fn = OllamaEmbeddingFunction(
        url=f"{Config.OLLAMA_URL}/api/embeddings",
        model_name="nomic-embed-text",
    )
    return client.get_or_create_collection(
        "ka_transcripts",
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )


def chunk_transcript(text: str, concept: dict, video_id: str, title: str) -> list[dict]:
    """Split transcript into CHUNK_WORDS-word chunks with metadata."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), CHUNK_WORDS):
        chunk_text = " ".join(words[i : i + CHUNK_WORDS])
        if len(chunk_text) < 80:
            continue
        chunk_id = f"{concept['id']}_{video_id}_{i}"
        chunks.append({
            "id":       chunk_id,
            "text":     chunk_text,
            "metadata": {
                "concept_id": concept["id"],
                "subject":    concept["subject"],
                "grade_min":  str(concept["grade_min"]),
                "grade_max":  str(concept["grade_max"]),
                "video_id":   video_id,
                "title":      title[:120],
                "source":     "khan_academy",
            },
        })
    return chunks


def embed_chunks(collection, chunks: list[dict]):
    if not chunks:
        return
    # Check which IDs already exist
    existing = set(collection.get(ids=[c["id"] for c in chunks])["ids"])
    new_chunks = [c for c in chunks if c["id"] not in existing]
    if not new_chunks:
        return
    collection.add(
        ids=[c["id"] for c in new_chunks],
        documents=[c["text"] for c in new_chunks],
        metadatas=[c["metadata"] for c in new_chunks],
    )


# ── Main pipeline ────────────────────────────────────────────────────────────

async def main():
    t_start = time.time()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   Parth Knowledge Graph — Overnight Ingestion Pipeline       ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    progress = load_progress()
    print(f"\nResume state: {sum(len(v) for v in progress['videos_done'].values())} videos already done")

    # ── Phase 1: Postgres (optional — skipped if Docker not running) ───────────
    try:
        conn = await asyncio.wait_for(asyncpg.connect(PG_DSN), timeout=5)
        await seed_postgres(conn)
        await conn.close()
        _pg_available = True
    except Exception as e:
        print(f"\n  ⚠  Postgres not available ({e.__class__.__name__}) — skipping DB phase.")
        print("     Run 'docker compose up -d' then re-run this script to seed Postgres.")
        _pg_available = False

    # ── Phase 2+3+4: Per-concept YouTube → transcript → embed ───────────────
    print("\n── Phase 2-4: YouTube search → transcripts → ChromaDB ──────────")
    collection = get_ka_collection()
    print(f"  ChromaDB 'ka_transcripts' has {collection.count()} chunks so far")

    total_new_videos   = 0
    total_new_chunks   = 0
    total_failed       = 0

    concept_bar = tqdm(NCERT_CONCEPTS, desc="Concepts", unit="concept")
    for concept in concept_bar:
        cid = concept["id"]
        concept_bar.set_description(f"{concept['label'][:35]}")
        done_for_concept = set(progress["videos_done"].get(cid, []))

        # Search YouTube
        query   = KA_QUERIES.get(cid, concept["label"])
        videos  = search_ka_videos(cid, query)
        new_videos = [v for v in videos if v["id"] not in done_for_concept]

        if not new_videos:
            tqdm.write(f"  {cid}: already done ({len(done_for_concept)} videos)")
            time.sleep(SEARCH_DELAY)
            continue

        tqdm.write(f"\n  {concept['label']}: found {len(videos)} KA videos, {len(new_videos)} new")

        video_ids_for_concept = list(done_for_concept)

        for video in new_videos:
            vid_id = video["id"]
            title  = video["title"]

            time.sleep(TRANSCRIPT_DELAY)
            transcript = get_transcript(vid_id)
            if not transcript:
                tqdm.write(f"    ✗ no transcript: {title[:60]}")
                total_failed += 1
                progress["failed_videos"].append(vid_id)
                continue

            # Chunk + embed (sync ChromaDB call)
            chunks = chunk_transcript(transcript, concept, vid_id, title)
            try:
                embed_chunks(collection, chunks)
            except Exception as e:
                tqdm.write(f"    ✗ embed error for {vid_id}: {e}")
                total_failed += 1
                continue

            # Record in Postgres (if available)
            if _pg_available:
                try:
                    _conn = await asyncpg.connect(PG_DSN)
                    await _conn.execute("""
                        INSERT INTO curriculum_graph.ka_videos
                            (video_id, concept_id, title, transcript_chars, embedded)
                        VALUES ($1,$2,$3,$4,true)
                        ON CONFLICT (video_id, concept_id) DO UPDATE
                        SET title=$3, transcript_chars=$4, embedded=true
                    """, vid_id, cid, title[:500], len(transcript))
                    await _conn.execute("""
                        UPDATE curriculum_graph.concepts
                        SET video_ids = array_append(
                            array_remove(video_ids, $2), $2
                        )
                        WHERE id = $1
                    """, cid, vid_id)
                    await _conn.close()
                except Exception:
                    pass

            video_ids_for_concept.append(vid_id)
            total_new_videos += 1
            total_new_chunks += len(chunks)
            tqdm.write(f"    ✓ {len(chunks)} chunks — {title[:60]}")

            # Save progress + JSON graph after each video
            progress["videos_done"][cid] = video_ids_for_concept
            save_progress(progress)
            save_graph_json(progress)

        time.sleep(SEARCH_DELAY)

    # ── Phase 5: Summary ────────────────────────────────────────────────────
    elapsed = int(time.time() - t_start)
    print(f"\n╔══════════════════════════════════════════════════════════════╗")
    print(f"║  Done in {elapsed//60}m {elapsed%60}s")
    print(f"║  New videos embedded : {total_new_videos}")
    print(f"║  New ChromaDB chunks : {total_new_chunks}")
    print(f"║  Failed (no transcript): {total_failed}")
    print(f"║  Total ka_transcripts: {collection.count()} chunks")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print("\n  Open the graph: http://localhost:8000/graph")
    print("  (start the server first with ./start.sh)\n")


if __name__ == "__main__":
    asyncio.run(main())

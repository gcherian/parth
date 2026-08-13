"""
NCERT + Khan Academy content ingestion — the single pipeline that
populates the ONE Chroma collection ("ncert") the live retrieval path
(modules/curriculum_graph/graph.py) actually queries.

Consolidates the two previously-separate, previously-disconnected
scripts (rag/ingest.py -> "ncert_curriculum", rag/ingest_graph.py's
Phases 2-4 -> "ka_transcripts", neither matching what graph.py queried).
rag/ingest_graph.py's Phase 1 (Postgres concept/edge seeding) is not
ported here — data/curriculum_seed.sql already seeds curriculum_graph
far more thoroughly and already runs on every apply_schema(); porting a
second, thinner seeder would be exactly the "two systems for one thing"
problem this refactor exists to remove. The NCERT_CONCEPTS/NCERT_EDGES
data those Postgres inserts used still exists — ingest/concept_graph_data.py.

Both content phases below share one embedding model (bge-m3, via Ollama
-- materially better Hindi/Hinglish retrieval than nomic-embed-text,
which matters for Parth's code-switching design) and one unified chunk
metadata shape: subject, grade (single int), chapter, board, school_id,
source. Embedding is NOT done manually per-chunk -- the collection's own
OllamaEmbeddingFunction embeds on .upsert(), the same auto-embed pattern
the live query path already relies on, so ingestion and retrieval can
never drift onto different embedding calls.

Different vector space than the old nomic-embed-text collections, so
this is a full re-ingestion, not an incremental add — matches the ticket's
own instruction not to attempt incremental re-embedding.

Run:  python -m ingest.build_index
"""
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=False)  # DATA_DIR/OLLAMA_URL are frequently .env-overridden
                               # (this deployment's own .env sets DATA_DIR explicitly) —
                               # must match main.py's own load_dotenv() call, or this
                               # script and the live server silently write/read two
                               # different Chroma paths, exactly as happened before this
                               # line was added.

import chromadb
import httpx
import pdfplumber
import yt_dlp
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
from tqdm import tqdm
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import Config
from ingest.concept_graph_data import NCERT_CONCEPTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("ingest.build_index")

COLLECTION_NAME = "ncert"
EMBED_MODEL = "bge-m3"
BOARD = "cbse"          # the only board with content this pass — field exists on every
                          # chunk so a future ICSE/state-board addition is a data problem,
                          # not a second schema migration
PDF_DIR = Config.DATA_DIR / "ncert"
PDF_DIR.mkdir(parents=True, exist_ok=True)

# ── NCERT PDF catalogue (grade, subject, chapter_code, chapter_title, pdf_url) ──
NCERT_PDF_CATALOGUE = [
    # Grade 6
    (6, "science",    "hesc101","Food: Where Does It Come From?",       "https://ncert.nic.in/textbook/pdf/hesc101.pdf"),
    (6, "science",    "hesc102","Components of Food",                    "https://ncert.nic.in/textbook/pdf/hesc102.pdf"),
    (6, "science",    "hesc108","Body Movements",                        "https://ncert.nic.in/textbook/pdf/hesc108.pdf"),
    (6, "science",    "hesc110","Motion and Measurement of Distances",   "https://ncert.nic.in/textbook/pdf/hesc110.pdf"),
    (6, "math",       "hemh101","Knowing Our Numbers",                   "https://ncert.nic.in/textbook/pdf/hemh101.pdf"),
    (6, "math",       "hemh102","Whole Numbers",                         "https://ncert.nic.in/textbook/pdf/hemh102.pdf"),
    (6, "math",       "hemh104","Basic Geometrical Ideas",               "https://ncert.nic.in/textbook/pdf/hemh104.pdf"),
    (6, "history",    "hess301","What, Where, How and When?",            "https://ncert.nic.in/textbook/pdf/hess301.pdf"),
    (6, "geography",  "hess201","The Earth in the Solar System",         "https://ncert.nic.in/textbook/pdf/hess201.pdf"),
    # Grade 7
    (7, "science",    "hesc701","Nutrition in Plants",                   "https://ncert.nic.in/textbook/pdf/hesc701.pdf"),
    (7, "science",    "hesc702","Nutrition in Animals",                  "https://ncert.nic.in/textbook/pdf/hesc702.pdf"),
    (7, "science",    "hesc707","Weather, Climate and Adaptations",      "https://ncert.nic.in/textbook/pdf/hesc707.pdf"),
    (7, "science",    "hesc710","Electric Current and Its Effects",      "https://ncert.nic.in/textbook/pdf/hesc710.pdf"),
    (7, "math",       "hemh701","Integers",                              "https://ncert.nic.in/textbook/pdf/hemh701.pdf"),
    (7, "math",       "hemh702","Fractions and Decimals",                "https://ncert.nic.in/textbook/pdf/hemh702.pdf"),
    (7, "math",       "hemh706","Triangles",                             "https://ncert.nic.in/textbook/pdf/hemh706.pdf"),
    (7, "history",    "hess701","Tracing Changes Through a Thousand Years","https://ncert.nic.in/textbook/pdf/hess701.pdf"),
    # Grade 8
    (8, "science",    "hesc801","Crop Production and Management",        "https://ncert.nic.in/textbook/pdf/hesc801.pdf"),
    (8, "science",    "hesc806","Combustion and Flame",                  "https://ncert.nic.in/textbook/pdf/hesc806.pdf"),
    (8, "science",    "hesc811","Force and Pressure",                    "https://ncert.nic.in/textbook/pdf/hesc811.pdf"),
    (8, "science",    "hesc812","Friction",                              "https://ncert.nic.in/textbook/pdf/hesc812.pdf"),
    (8, "math",       "hemh801","Rational Numbers",                      "https://ncert.nic.in/textbook/pdf/hemh801.pdf"),
    (8, "math",       "hemh804","Practical Geometry",                    "https://ncert.nic.in/textbook/pdf/hemh804.pdf"),
    (8, "math",       "hemh811","Mensuration",                           "https://ncert.nic.in/textbook/pdf/hemh811.pdf"),
    (8, "history",    "hess801","How, When and Where",                   "https://ncert.nic.in/textbook/pdf/hess801.pdf"),
    # Grade 9
    (9, "science",    "jesc101","Matter in Our Surroundings",            "https://ncert.nic.in/textbook/pdf/jesc101.pdf"),
    (9, "science",    "jesc102","Is Matter Around Us Pure?",             "https://ncert.nic.in/textbook/pdf/jesc102.pdf"),
    (9, "science",    "jesc108","Motion",                                "https://ncert.nic.in/textbook/pdf/jesc108.pdf"),
    (9, "science",    "jesc109","Force and Laws of Motion",              "https://ncert.nic.in/textbook/pdf/jesc109.pdf"),
    (9, "science",    "jesc113","Why Do We Fall Ill",                    "https://ncert.nic.in/textbook/pdf/jesc113.pdf"),
    (9, "math",       "jemh101","Number Systems",                        "https://ncert.nic.in/textbook/pdf/jemh101.pdf"),
    (9, "math",       "jemh104","Linear Equations in Two Variables",     "https://ncert.nic.in/textbook/pdf/jemh104.pdf"),
    (9, "math",       "jemh109","Areas of Parallelograms and Triangles", "https://ncert.nic.in/textbook/pdf/jemh109.pdf"),
    (9, "history",    "jess301","The French Revolution",                 "https://ncert.nic.in/textbook/pdf/jess301.pdf"),
    (9, "geography",  "jess201","India — Size and Location",             "https://ncert.nic.in/textbook/pdf/jess201.pdf"),
    # Grade 10
    (10,"science",    "lesc101","Chemical Reactions and Equations",      "https://ncert.nic.in/textbook/pdf/lesc101.pdf"),
    (10,"science",    "lesc106","Life Processes",                        "https://ncert.nic.in/textbook/pdf/lesc106.pdf"),
    (10,"science",    "lesc110","Light — Reflection and Refraction",     "https://ncert.nic.in/textbook/pdf/lesc110.pdf"),
    (10,"math",       "lemh101","Real Numbers",                          "https://ncert.nic.in/textbook/pdf/lemh101.pdf"),
    (10,"math",       "lemh103","Pair of Linear Equations in Two Variables","https://ncert.nic.in/textbook/pdf/lemh103.pdf"),
    (10,"math",       "lemh107","Coordinate Geometry",                   "https://ncert.nic.in/textbook/pdf/lemh107.pdf"),
    (10,"history",    "less301","The Rise of Nationalism in Europe",     "https://ncert.nic.in/textbook/pdf/less301.pdf"),
]

# ── Khan Academy search queries per concept (subset of NCERT_CONCEPTS worth
#    finding video coverage for) ────────────────────────────────────────────
KA_QUERIES = {
    "arithmetic":          "arithmetic basic operations numbers",
    "fractions":           "fractions introduction numerator denominator",
    "decimals":            "decimals introduction place value",
    "bodmas":               "order of operations PEMDAS BODMAS",
    "ratios":               "ratios and proportions introduction",
    "geometry":              "basic geometry angles triangles area",
    "algebra_basics":       "introduction to algebra variables equations",
    "cell_biology":          "cell structure function biology",
    "photosynthesis":        "photosynthesis how plants make food",
    "human_body":            "human body systems overview",
    "ecosystem":             "ecosystems food chains energy",
    "water_cycle":           "water cycle evaporation condensation",
    "newton_laws":           "Newton's laws of motion force",
    "electricity":           "electricity circuits current voltage",
    "magnetism":             "magnetism magnetic fields electromagnetism",
    "light_optics":          "light reflection refraction optics",
    "sound":                 "sound waves frequency pitch",
    "periodic_table":        "periodic table elements atoms",
    "mughal_empire":         "Mughal empire history India Akbar",
    "indian_independence":   "Indian independence movement Gandhi",
}
VIDEOS_PER_CONCEPT = 3   # kept modest — this script now runs as part of a single
                          # pass a developer runs interactively, not an overnight job
CHUNK_WORDS_KA = 150
SEARCH_DELAY = 2.0
TRANSCRIPT_DELAY = 1.0


def get_collection():
    chroma_path = Config.DATA_DIR / "chroma"
    chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_path))
    embed_fn = OllamaEmbeddingFunction(
        url=f"{Config.OLLAMA_URL}/api/embeddings",
        model_name=EMBED_MODEL,
    )
    return client.get_or_create_collection(
        COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(collection, chunks: list[dict]) -> int:
    """chunks: [{id, text, metadata}]. Upsert is idempotent — safe to
    re-run this whole script without duplicating existing chunks."""
    if not chunks:
        return 0
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    return len(chunks)


# ── Phase A: NCERT PDF textbook content ─────────────────────────────────────

def download_pdf(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 10_000:
        return True
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            r = client.get(url)
            if r.status_code == 200 and len(r.content) > 5_000:
                dest.write_bytes(r.content)
                return True
    except Exception as e:
        log.warning(f"  download failed {url}: {e}")
    return False


def extract_text(pdf_path: Path) -> str:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = [p.extract_text() for p in pdf.pages]
        return "\n\n".join(p for p in pages if p)
    except Exception as e:
        log.warning(f"  extract failed {pdf_path}: {e}")
        return ""


def chunk_words(text: str, size: int = 400, overlap: int = 60) -> list[str]:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunk_text = " ".join(words[i:i + size]).strip()
        if len(chunk_text) > 80:
            chunks.append(chunk_text)
        i += size - overlap
    return chunks


def ingest_ncert_pdfs(collection) -> tuple[int, int]:
    log.info(f"Phase A: NCERT PDFs — {len(NCERT_PDF_CATALOGUE)} chapters")
    ingested, failed = 0, 0

    for grade, subject, code, title, url in tqdm(NCERT_PDF_CATALOGUE, desc="PDF chapters"):
        pdf_path = PDF_DIR / f"{code}.pdf"
        if not download_pdf(url, pdf_path):
            log.warning(f"  SKIP {code} (download failed)")
            failed += 1
            continue

        text = extract_text(pdf_path)
        if not text or len(text) < 200:
            log.warning(f"  SKIP {code} (no text extracted)")
            failed += 1
            continue

        chunks = [
            {
                "id": f"pdf_{code}_{i}",
                "text": chunk_text,
                "metadata": {
                    "subject": subject.lower(),
                    "grade": grade,
                    "chapter": title,
                    "board": BOARD,
                    "school_id": "",   # Chroma metadata can't store None; empty = unset
                    "source": "ncert_pdf",
                },
            }
            for i, chunk_text in enumerate(chunk_words(text))
        ]
        ingested += upsert_chunks(collection, chunks)
        time.sleep(0.1)

    return ingested, failed


# ── Phase B: Khan Academy transcripts ───────────────────────────────────────

def search_ka_videos(query: str, n: int) -> list[dict]:
    ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "ignoreerrors": True}
    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{n * 2}:Khan Academy {query}", download=False)
            for entry in (info or {}).get("entries") or []:
                if not entry or not entry.get("id"):
                    continue
                if (entry.get("duration") or 999) < 1500:
                    results.append({"id": entry["id"], "title": entry.get("title", "")})
                if len(results) >= n:
                    break
    except Exception as e:
        log.warning(f"    search error: {e}")
    return results


def get_transcript(video_id: str) -> str:
    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(s["text"] for s in segments)
    except (NoTranscriptFound, TranscriptsDisabled):
        try:
            t = YouTubeTranscriptApi.list_transcripts(video_id).find_generated_transcript(["en", "en-US"])
            return " ".join(s["text"] for s in t.fetch())
        except Exception:
            return ""
    except Exception:
        return ""


def ingest_khan_academy(collection) -> tuple[int, int]:
    log.info(f"Phase B: Khan Academy — {len(KA_QUERIES)} concepts")
    concept_by_id = {c["id"]: c for c in NCERT_CONCEPTS}
    ingested, failed = 0, 0

    for concept_id, query in tqdm(KA_QUERIES.items(), desc="KA concepts"):
        concept = concept_by_id.get(concept_id)
        if concept is None:
            continue

        videos = search_ka_videos(query, VIDEOS_PER_CONCEPT)
        time.sleep(SEARCH_DELAY)

        for video in videos:
            time.sleep(TRANSCRIPT_DELAY)
            transcript = get_transcript(video["id"])
            if not transcript:
                failed += 1
                continue

            words = transcript.split()
            chunks = [
                {
                    "id": f"ka_{concept_id}_{video['id']}_{i}",
                    "text": " ".join(words[i:i + CHUNK_WORDS_KA]),
                    "metadata": {
                        "subject": concept["subject"].lower(),
                        # A chunk is relevant from grade_min onward — consistent
                        # with curriculum_graph's own grade_min/grade_max
                        # prerequisite treatment elsewhere in this codebase.
                        "grade": concept["grade_min"],
                        "chapter": concept["label"],
                        "board": BOARD,
                        "school_id": "",
                        "source": "khan_academy",
                    },
                }
                for i in range(0, len(words), CHUNK_WORDS_KA)
                if len(" ".join(words[i:i + CHUNK_WORDS_KA])) > 80
            ]
            ingested += upsert_chunks(collection, chunks)

    return ingested, failed


# ── Main ─────────────────────────────────────────────────────────────────────

def run(skip_khan_academy: bool = False):
    collection = get_collection()
    log.info(f"Collection '{COLLECTION_NAME}' has {collection.count()} chunks before this run")

    pdf_ingested, pdf_failed = ingest_ncert_pdfs(collection)

    ka_ingested, ka_failed = (0, 0)
    if not skip_khan_academy:
        ka_ingested, ka_failed = ingest_khan_academy(collection)
    else:
        log.info("Phase B skipped (skip_khan_academy=True)")

    total = collection.count()
    log.info(
        f"Done. PDF chunks: {pdf_ingested} ({pdf_failed} chapters failed). "
        f"KA chunks: {ka_ingested} ({ka_failed} videos failed). "
        f"Collection '{COLLECTION_NAME}' total: {total} chunks."
    )
    return total


if __name__ == "__main__":
    skip_ka = "--skip-khan-academy" in sys.argv
    run(skip_khan_academy=skip_ka)

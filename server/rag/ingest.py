"""
NCERT content ingestion pipeline.
Downloads PDFs from ncert.nic.in, extracts text, chunks, embeds, stores in ChromaDB.
Run once:  python -m rag.ingest
"""
import hashlib
import logging
import os
import sys
import time
from pathlib import Path

import httpx
import pdfplumber
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import Config
from rag.embedder import embed_sync
from rag.store import count, upsert

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("ingest")

DATA_DIR = Config.DATA_DIR / "ncert"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── NCERT PDF catalogue ───────────────────────────────────────────────────────
# Format: (grade, subject, chapter_num, chapter_title, pdf_url)
# Using NCERT's open-access PDFs (CC-licensed, free to use)
NCERT_CATALOGUE = [
    # Grade 6
    (6, "science",    "hemh1",  "Food: Where Does It Come From?",       "https://ncert.nic.in/textbook/pdf/hesc101.pdf"),
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
    (10,"science",    "jesc101","Chemical Reactions and Equations",      "https://ncert.nic.in/textbook/pdf/lesc101.pdf"),
    (10,"science",    "lesc106","Life Processes",                        "https://ncert.nic.in/textbook/pdf/lesc106.pdf"),
    (10,"science",    "lesc110","Light — Reflection and Refraction",     "https://ncert.nic.in/textbook/pdf/lesc110.pdf"),
    (10,"math",       "lemh101","Real Numbers",                          "https://ncert.nic.in/textbook/pdf/lemh101.pdf"),
    (10,"math",       "lemh103","Pair of Linear Equations in Two Variables","https://ncert.nic.in/textbook/pdf/lemh103.pdf"),
    (10,"math",       "lemh107","Coordinate Geometry",                   "https://ncert.nic.in/textbook/pdf/lemh107.pdf"),
    (10,"history",    "less301","The Rise of Nationalism in Europe",     "https://ncert.nic.in/textbook/pdf/less301.pdf"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

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
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n\n".join(pages)
    except Exception as e:
        log.warning(f"  extract failed {pdf_path}: {e}")
        return ""


def chunk(text: str, size: int = 400, overlap: int = 60) -> list[str]:
    """Split text into overlapping word-level chunks."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i : i + size]
        chunk_text = " ".join(chunk_words).strip()
        if len(chunk_text) > 80:
            chunks.append(chunk_text)
        i += size - overlap
    return chunks


# ── Main ingestion loop ───────────────────────────────────────────────────────

def run():
    log.info(f"Starting NCERT ingestion — {len(NCERT_CATALOGUE)} chapters")
    log.info(f"ChromaDB already has {count()} chunks")

    ingested = 0
    skipped = 0
    failed = 0

    for grade, subject, code, title, url in tqdm(NCERT_CATALOGUE, desc="Chapters"):
        pdf_path = DATA_DIR / f"{code}.pdf"

        log.info(f"  Grade {grade} {subject.title()} — {title}")

        if not download_pdf(url, pdf_path):
            log.warning(f"  SKIP (download failed)")
            failed += 1
            continue

        text = extract_text(pdf_path)
        if not text or len(text) < 200:
            log.warning(f"  SKIP (no text extracted)")
            failed += 1
            continue

        chunks = chunk(text)
        log.info(f"  {len(chunks)} chunks → embedding...")

        for i, chunk_text in enumerate(chunks):
            doc_id = hashlib.md5(f"{code}_{i}".encode()).hexdigest()
            try:
                embedding = embed_sync(chunk_text)
                upsert(
                    doc_id=doc_id,
                    text=chunk_text,
                    embedding=embedding,
                    metadata={
                        "grade": grade,
                        "subject": subject,
                        "chapter": title,
                        "code": code,
                        "chunk_index": i,
                    },
                )
                ingested += 1
            except Exception as e:
                log.warning(f"  embed failed chunk {i}: {e}")
                skipped += 1

        time.sleep(0.1)  # be gentle with Ollama

    log.info(f"\nDone! Ingested {ingested} chunks, skipped {skipped}, failed {failed} chapters")
    log.info(f"ChromaDB total: {count()} chunks")


if __name__ == "__main__":
    run()

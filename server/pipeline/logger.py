import json
import logging
from datetime import datetime
from pathlib import Path

from config import Config
from learner.db import get_conn

LOG_DIR = Config.DATA_DIR / "logs"
log = logging.getLogger("parth.log")


def log_interaction(
    learner_id: str,
    subject: str,
    grade: int,
    question: str,
    response: str,
    model: str,
    duration_ms: int,
    misconception: str = "",
    emotion: str = "neutral",
    engagement: int = 5,
):
    ts = datetime.utcnow().isoformat()

    try:
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO interactions
                   (learner_id, ts, subject, grade, question, response, model,
                    duration_ms, misconception, emotion, engagement)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (learner_id, ts, subject, grade, question[:1000],
                 response[:2000], model, duration_ms, misconception, emotion, engagement),
            )
    except Exception as e:
        log.warning(f"DB log failed: {e}")

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        day = datetime.utcnow().strftime("%Y-%m-%d")
        with open(LOG_DIR / f"{day}.jsonl", "a") as f:
            json.dump({
                "ts": ts, "learner_id": learner_id, "subject": subject,
                "grade": grade, "question": question[:300],
                "response": response[:600], "model": model,
                "duration_ms": duration_ms, "misconception": misconception,
                "emotion": emotion, "engagement": engagement,
            }, f, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        log.warning(f"JSONL log failed: {e}")

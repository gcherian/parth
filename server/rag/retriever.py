import logging
from rag.embedder import embed
from rag.store import query, count

log = logging.getLogger("parth.rag")


async def retrieve(question: str, subject: str, grade: int, n: int = 3) -> str:
    """
    Retrieve the most relevant NCERT passages for a question.
    Returns a formatted context string to inject into the prompt.
    Falls back gracefully if the store is empty.
    """
    if count() == 0:
        return ""

    try:
        embedding = await embed(question)

        # Try subject + grade filtered first
        where = {"$and": [{"subject": subject.lower()}, {"grade": {"$lte": grade + 1}}]}
        passages = query(embedding, n_results=n, where=where)

        # Widen to just subject if not enough hits
        if len(passages) < 2:
            passages = query(embedding, n_results=n, where={"subject": subject.lower()})

        # Fall back to unfiltered
        if len(passages) < 2:
            passages = query(embedding, n_results=n)

        if not passages:
            return ""

        # Only include passages with reasonable relevance
        good = [p for p in passages if p["score"] > 0.35]
        if not good:
            return ""

        context_lines = []
        for p in good:
            meta = p["metadata"]
            label = f"[{meta.get('subject','').title()} Grade {meta.get('grade','?')} — {meta.get('chapter','')}]"
            context_lines.append(f"{label}\n{p['text']}")

        context = "\n\n".join(context_lines)
        log.debug(f"RAG: {len(good)} passages for '{question[:50]}' (subject={subject})")
        return context

    except Exception as e:
        log.warning(f"RAG retrieval failed: {e}")
        return ""

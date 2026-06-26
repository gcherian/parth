import httpx
from config import Config


async def embed(text: str) -> list[float]:
    """Embed text using nomic-embed-text via Ollama (already installed)."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{Config.OLLAMA_URL}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text},
        )
        r.raise_for_status()
        return r.json()["embedding"]


def embed_sync(text: str) -> list[float]:
    """Synchronous version for ingestion scripts."""
    import httpx as _httpx
    r = _httpx.post(
        f"{Config.OLLAMA_URL}/api/embeddings",
        json={"model": "nomic-embed-text", "prompt": text},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["embedding"]

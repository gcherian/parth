import chromadb
from chromadb.config import Settings

from config import Config

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None

COLLECTION_NAME = "ncert_curriculum"


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        chroma_path = Config.DATA_DIR / "chroma"
        chroma_path.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        _collection = _get_client().get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def upsert(doc_id: str, text: str, embedding: list[float], metadata: dict):
    get_collection().upsert(
        ids=[doc_id],
        documents=[text],
        embeddings=[embedding],
        metadatas=[metadata],
    )


def query(embedding: list[float], n_results: int = 4, where: dict | None = None) -> list[dict]:
    kwargs = dict(
        query_embeddings=[embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    if where:
        kwargs["where"] = where

    result = get_collection().query(**kwargs)

    passages = []
    for doc, meta, dist in zip(
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0],
    ):
        passages.append({"text": doc, "metadata": meta, "score": 1 - dist})
    return passages


def count() -> int:
    return get_collection().count()

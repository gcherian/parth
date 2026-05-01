import json
import logging
import time
from collections import defaultdict
from datetime import datetime

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("parth")

app = FastAPI(title="Parth AI Server", version="1.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiter ──────────────────────────────────────────────────────────────
_buckets: dict[str, list[float]] = defaultdict(list)


def rate_limit(request: Request):
    ip = request.client.host
    now = time.time()
    _buckets[ip] = [t for t in _buckets[ip] if now - t < 60]
    if len(_buckets[ip]) >= Config.RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Ek minute ruko! Too many questions at once — try again shortly.",
        )
    _buckets[ip].append(now)


# ── Request / Response models ─────────────────────────────────────────────────
class Message(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []
    subject: str = "General"
    model: str | None = None   # override default model


class ChatResponse(BaseModel):
    response: str
    model: str
    duration_ms: int


# ── Chat endpoint ─────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, _: None = Depends(rate_limit)):
    model = req.model or Config.DEFAULT_MODEL
    t0 = time.time()

    # Build message list for Ollama
    messages = [
        {
            "role": "user",
            "content": Config.system_prompt(req.subject),
        },
        {
            "role": "assistant",
            "content": "Namaste! I'm Parth, your personal AI mentor. Ask me anything!",
        },
    ]

    # Append recent conversation history (last 8 exchanges = 16 turns)
    for m in req.history[-16:]:
        messages.append({"role": m.role, "content": m.content})

    messages.append({"role": "user", "content": req.message})

    log.info(f"[{req.subject}] [{model}] {req.message[:80]!r}")

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(
                f"{Config.OLLAMA_URL}/api/chat",
                json={"model": model, "messages": messages, "stream": False},
            )
            r.raise_for_status()
    except httpx.TimeoutException:
        log.warning("Ollama timed out — switching to fast model")
        # Auto-fallback to faster model on timeout
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{Config.OLLAMA_URL}/api/chat",
                    json={
                        "model": Config.FAST_MODEL,
                        "messages": messages,
                        "stream": False,
                    },
                )
                r.raise_for_status()
                model = Config.FAST_MODEL
        except Exception as e:
            raise HTTPException(status_code=504, detail="AI is thinking hard — please try again in a moment!")
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Ollama is not running. Please start it with: ollama serve",
        )
    except Exception as e:
        log.error(f"Ollama error: {e}")
        raise HTTPException(status_code=503, detail=str(e))

    data = r.json()
    reply = data["message"]["content"]
    duration = int((time.time() - t0) * 1000)

    log.info(f"  ↳ {len(reply)} chars in {duration}ms")
    return ChatResponse(response=reply, model=model, duration_ms=duration)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            r = await client.get(f"{Config.OLLAMA_URL}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
        ollama_ok = True
    except Exception:
        models = []
        ollama_ok = False

    return {
        "status": "ok" if ollama_ok else "degraded",
        "ollama": ollama_ok,
        "default_model": Config.DEFAULT_MODEL,
        "fast_model": Config.FAST_MODEL,
        "available_models": models,
        "server_ip": Config.local_ip(),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Model list ────────────────────────────────────────────────────────────────
@app.get("/models")
async def list_models():
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{Config.OLLAMA_URL}/api/tags")
        return r.json()


# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    ip = Config.local_ip()
    return {
        "name": "Parth AI Server",
        "status": "running",
        "endpoints": {
            "chat": f"POST http://{ip}:{Config.PORT}/chat",
            "health": f"GET  http://{ip}:{Config.PORT}/health",
            "docs": f"GET  http://{ip}:{Config.PORT}/docs",
        },
    }

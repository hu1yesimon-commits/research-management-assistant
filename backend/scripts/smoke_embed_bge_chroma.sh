#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

TMP_ROOT="${TMPDIR:-/tmp}/graphreconstruction-bge-chroma-smoke"
DB_PATH="$TMP_ROOT/research_memory.sqlite3"
CHROMA_DIR="$TMP_ROOT/chroma"
UPLOAD_DIR="$TMP_ROOT/uploads"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8010}"
BASE_URL="http://${HOST}:${PORT}"
PAPER_ID="${PAPER_ID:-smoke-paper-1}"

rm -rf "$TMP_ROOT"
mkdir -p "$CHROMA_DIR" "$UPLOAD_DIR"

export TMP_ROOT="$TMP_ROOT"
export PAPER_ID="$PAPER_ID"
export DATABASE_PATH="$DB_PATH"
export PDF_UPLOAD_DIR="$UPLOAD_DIR"
export VECTOR_BACKEND="chroma"
export CHROMA_PERSIST_DIR="$CHROMA_DIR"
export CHROMA_COLLECTION_NAME="research_chunks"
export EMBEDDING_PROVIDER="bge-m3"
export BGE_M3_MODEL_NAME="${BGE_M3_MODEL_NAME:-BAAI/bge-m3}"
export PYTHONPATH="backend/src"

echo "SMOKE_TMP_ROOT=$TMP_ROOT"
echo "DATABASE_PATH=$DATABASE_PATH"
echo "CHROMA_PERSIST_DIR=$CHROMA_PERSIST_DIR"
echo "EMBEDDING_PROVIDER=$EMBEDDING_PROVIDER"
echo "VECTOR_BACKEND=$VECTOR_BACKEND"

./.venv/bin/python - <<'PY'
from services.memory_store import MemoryStore
from services.schemas import JudgeResult, PaperId, PaperMetadata

import os

store = MemoryStore(os.environ["DATABASE_PATH"])
store.initialize()

paper_id = os.environ["PAPER_ID"] if "PAPER_ID" in os.environ else "smoke-paper-1"
paper = PaperMetadata(
    paper_id=paper_id,
    source_ids=PaperId(doi=f"10.1000/{paper_id}"),
    title="Smoke Paper",
    authors=["Smoke Tester"],
    abstract="Manual integration smoke for BGE-M3 and Chroma.",
    doi=f"10.1000/{paper_id}",
    source="test",
)
judgement = JudgeResult(
    decision="accept",
    reason="smoke seed",
    llm_relevance_score=0.9,
    embedding_relevance_score=0.8,
    quality_score=0.7,
    novelty_score=0.6,
    final_score=0.75,
    tags=["smoke"],
)

store.save_candidate_paper(paper, judgement)
store.update_paper_status(paper_id, "uploaded", pdf_path=os.path.join(os.environ["PDF_UPLOAD_DIR"], "smoke.pdf"))
store.insert_knowledge_chunks(
    paper_id,
    [
        {
            "chunk_index": 0,
            "text": "This is the first smoke chunk for real BGE-M3 plus Chroma integration.",
            "chunk_hash": "smoke-hash-0",
            "vector_ref": None,
        },
        {
            "chunk_index": 1,
            "text": "This is the second smoke chunk to verify all persisted chunks receive vector refs.",
            "chunk_hash": "smoke-hash-1",
            "vector_ref": None,
        },
    ],
)
store.update_paper_status(paper_id, "chunked")
print(f"SEEDED_PAPER_ID={paper_id}")
PY

SERVER_LOG="$TMP_ROOT/uvicorn.log"
./.venv/bin/uvicorn main:app --app-dir backend/src --host "$HOST" --port "$PORT" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 60); do
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
  echo "ERROR: uvicorn did not become healthy"
  echo "---- uvicorn.log ----"
  cat "$SERVER_LOG"
  exit 1
fi

RESPONSE_FILE="$TMP_ROOT/embed_response.json"
HTTP_CODE="$(curl -sS -o "$RESPONSE_FILE" -w "%{http_code}" -X POST "$BASE_URL/papers/$PAPER_ID/embed")"
if [[ "$HTTP_CODE" != "200" ]]; then
  echo "ERROR: embed request failed with HTTP $HTTP_CODE"
  cat "$RESPONSE_FILE"
  echo
  echo "---- uvicorn.log ----"
  cat "$SERVER_LOG"
  exit 1
fi

echo "EMBED_RESPONSE=$(cat "$RESPONSE_FILE")"

./.venv/bin/python - <<'PY'
import json
import os

from chromadb import PersistentClient
from services.memory_store import MemoryStore

paper_id = os.environ["PAPER_ID"] if "PAPER_ID" in os.environ else "smoke-paper-1"
response_path = os.path.join(os.environ["TMP_ROOT"], "embed_response.json")
store = MemoryStore(os.environ["DATABASE_PATH"])

with open(response_path, "r", encoding="utf-8") as fh:
    body = json.load(fh)

if body.get("status") != "embedded":
    raise SystemExit(f"expected embedded status, got: {body}")

chunks = store.list_knowledge_chunks(paper_id)
if not chunks:
    raise SystemExit("no chunks found after embed")
if any(not chunk["vector_ref"] or not chunk["vector_ref"].strip() for chunk in chunks):
    raise SystemExit(f"expected all chunks to have non-empty vector_ref, got: {chunks}")

client = PersistentClient(path=os.environ["CHROMA_PERSIST_DIR"])
collection = client.get_collection(name=os.environ["CHROMA_COLLECTION_NAME"])
chunk_ids = [f"{paper_id}:{chunk['chunk_index']}:{chunk['chunk_hash']}" for chunk in chunks]
payload = collection.get(ids=chunk_ids)
if payload["ids"] != chunk_ids:
    raise SystemExit(f"expected Chroma ids {chunk_ids}, got: {payload['ids']}")

print(f"SQLITE_VECTOR_REF_COUNT={len(chunks)}")
print("SQLITE_VECTOR_REFS_OK=true")
print(f"CHROMA_ID_COUNT={len(payload['ids'])}")
print("CHROMA_WRITE_OK=true")
PY

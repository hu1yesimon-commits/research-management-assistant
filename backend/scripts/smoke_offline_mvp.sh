#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="backend/src"
export PAPER_JUDGE_PROVIDER="mock"
export EMBEDDING_PROVIDER="fake"
export VECTOR_BACKEND="fake"
export ANSWER_PROVIDER="deterministic"
export IDEA_PROVIDER="deterministic"

./.venv/bin/python - <<'PY'
import os
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path.cwd()
sys.path.insert(0, str(ROOT_DIR / "backend" / "src"))

with tempfile.TemporaryDirectory(prefix="graphreconstruction-offline-smoke-") as tmp_dir:
    os.environ["DATABASE_PATH"] = str(Path(tmp_dir) / "research_memory.sqlite3")
    os.environ["PDF_UPLOAD_DIR"] = str(Path(tmp_dir) / "uploads")
    os.environ["PAPER_JUDGE_PROVIDER"] = "mock"
    os.environ["EMBEDDING_PROVIDER"] = "fake"
    os.environ["VECTOR_BACKEND"] = "fake"
    os.environ["ANSWER_PROVIDER"] = "deterministic"
    os.environ["IDEA_PROVIDER"] = "deterministic"

    from fastapi.testclient import TestClient

    from main import app, get_embedding_service, get_memory_store, get_vector_store_service
    from services.embedding_service import FakeEmbeddingService
    from services.memory_store import MemoryStore
    from services.schemas import JudgeResult, PaperId, PaperMetadata
    from services.vector_store import FakeVectorStoreService

    store = MemoryStore(os.environ["DATABASE_PATH"])
    store.initialize()
    vector_store = FakeVectorStoreService()
    embedding_service = FakeEmbeddingService()

    app.dependency_overrides[get_memory_store] = lambda: store
    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_vector_store_service] = lambda: vector_store

    client = TestClient(app)

    def assert_status(response, expected_status=200):
        if response.status_code != expected_status:
            raise SystemExit(
                f"expected HTTP {expected_status}, got {response.status_code}: {response.text}"
            )
        return response.json()

    experiment_log = {
        "task": "defect classification",
        "model": "1D-CNN",
        "dataset": "bearing fault dataset",
        "metric_problem": "minority class PRAUC is low",
        "tried_methods": ["focal loss"],
        "observation": "recall improves but precision collapses",
        "goal": "improve PRAUC without making model too heavy",
        "tags": ["lightweight"],
    }

    health = assert_status(client.get("/health"))
    print(f"HEALTH_STATUS={health['status']}")

    for _ in range(3):
        created = assert_status(client.post("/experiments/logs", json=experiment_log))
        if created["id"] <= 0:
            raise SystemExit(f"expected positive experiment log id, got: {created}")

    logs = assert_status(client.get("/experiments/logs"))
    if len(logs) != 3:
        raise SystemExit(f"expected 3 experiment logs, got: {len(logs)}")
    print(f"EXPERIMENT_LOG_COUNT={len(logs)}")

    candidates = assert_status(client.post("/memory/candidates/refresh"))
    if not candidates:
        raise SystemExit("expected memory candidates after repeated structured logs")
    print(f"MEMORY_CANDIDATE_COUNT={len(candidates)}")

    accepted_memory = assert_status(client.post(f"/memory/candidates/{candidates[0]['id']}/accept"))
    if accepted_memory["status"] != "confirmed":
        raise SystemExit(f"expected confirmed semantic memory, got: {accepted_memory}")
    print(f"MEMORY_ACCEPTED_STATUS={accepted_memory['status']}")

    paper = PaperMetadata(
        paper_id="idea-evidence-paper-1",
        source_ids=PaperId(doi="10.1000/idea-evidence-paper-1"),
        title="Evidence Paper For Minority PRAUC",
        authors=["Smoke Tester"],
        abstract="A local evidence paper about focal loss and precision recall tradeoffs.",
        doi="10.1000/idea-evidence-paper-1",
        source="smoke",
    )
    judgement = JudgeResult(
        decision="accept",
        reason="offline smoke seed",
        llm_relevance_score=0.9,
        embedding_relevance_score=0.8,
        quality_score=0.7,
        novelty_score=0.6,
        final_score=0.75,
        tags=["smoke"],
    )
    chunk_text = (
        "Focal loss can improve recall under class imbalance, but precision and PRAUC "
        "often need threshold tuning or calibration."
    )
    chunk = {
        "chunk_uid": "idea-evidence-paper-1:0:idea-hash-0",
        "paper_id": paper.paper_id,
        "chunk_index": 0,
        "text": chunk_text,
    }
    vector_ref = vector_store.upsert_chunks(
        [chunk],
        embeddings=embedding_service.embed_texts([chunk_text]),
    )[0]
    store.save_candidate_paper(paper, judgement)
    store.update_paper_status(paper.paper_id, "embedded", pdf_path=str(Path(tmp_dir) / "evidence.pdf"))
    store.insert_knowledge_chunks(
        paper.paper_id,
        [
            {
                "chunk_index": 0,
                "text": chunk_text,
                "chunk_hash": "idea-hash-0",
                "vector_ref": vector_ref,
            }
        ],
    )

    idea_response = assert_status(
        client.post(
            "/ideas/recommend",
            json={
                "experiment_log": experiment_log,
                "save_log": True,
                "include_discovery": False,
                "top_k": 5,
                "idea_count": 3,
            },
        )
    )

    ideas = idea_response["ideas"]
    if len(ideas) != 3:
        raise SystemExit(f"expected 3 ideas, got: {len(ideas)}")

    first_evidence = ideas[0]["supporting_evidence"]
    if not first_evidence:
        raise SystemExit(f"expected non-empty supporting_evidence, got: {ideas[0]}")

    evidence = first_evidence[0]
    if evidence["source_type"] != "knowledge":
        raise SystemExit(f"expected knowledge evidence, got: {evidence}")
    if evidence["paper_id"] != paper.paper_id:
        raise SystemExit(f"expected evidence from seeded paper, got: {evidence}")
    if evidence["vector_ref"] != vector_ref:
        raise SystemExit(f"expected evidence vector_ref {vector_ref}, got: {evidence}")

    print(f"IDEA_MODE={idea_response['mode']}")
    print(f"IDEA_COUNT={len(ideas)}")
    print(f"IDEA_EVIDENCE_COUNT={len(first_evidence)}")
    print(f"IDEA_EVIDENCE_PAPER_ID={evidence['paper_id']}")
    print("OFFLINE_MVP_SMOKE_OK=true")

    app.dependency_overrides.clear()
PY

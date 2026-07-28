import importlib.util
import sqlite3
from pathlib import Path

from services.candidate_lifecycle import CandidateLifecycleService
from services.memory_store import MemoryStore
from services.schemas import JudgeResult, PaperId, PaperMetadata
from services.session_store import SessionStore


def _load_reset_script():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "reset_demo_session.py"
    spec = importlib.util.spec_from_file_location("reset_demo_session", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _paper(paper_id: str) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        source_ids=PaperId(doi=f"10.1000/{paper_id}"),
        title=f"Paper {paper_id}",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi=f"10.1000/{paper_id}",
        source="test",
    )


def _judgement() -> JudgeResult:
    return JudgeResult(
        decision="accept",
        reason="Relevant",
        llm_relevance_score=0.9,
        embedding_relevance_score=0.8,
        quality_score=0.7,
        novelty_score=0.6,
        final_score=0.82,
        tags=["demo"],
    )


def test_reset_demo_session_clears_default_session_but_preserves_saved_papers(tmp_path):
    database_path = tmp_path / "reset-demo.sqlite3"
    memory_store = MemoryStore(str(database_path))
    memory_store.initialize()
    session_store = SessionStore(str(database_path))
    candidate_service = CandidateLifecycleService(str(database_path))

    saved_paper = _paper("saved-paper")
    memory_store.save_candidate_paper(saved_paper, _judgement())
    memory_store.update_paper_status(
        saved_paper.paper_id,
        "embedded",
        pdf_path="/tmp/saved-paper.pdf",
    )
    memory_store.insert_knowledge_chunks(
        saved_paper.paper_id,
        [
            {
                "chunk_index": 0,
                "text": "Saved paper chunk",
                "chunk_hash": "saved-chunk",
                "vector_ref": "fake:saved-paper:0",
            }
        ],
    )

    turn = session_store.start_turn("default", "demo-turn", {"text": "Find papers"})
    session_store.complete_turn(
        turn.turn_id,
        {"assistant_message": "Found candidates"},
        {"plan_type": "research"},
    )
    latest_message_id = session_store.latest_message_id("default")
    session_store.update_session_summary("default", "old summary", latest_message_id)
    session_store.upsert_agent_context(
        "default",
        "research",
        "research context",
        latest_message_id,
    )
    run_id = session_store.start_agent_run(
        "default",
        turn.turn_id,
        "research",
        "recommend_papers",
        {"query": "graph reconstruction"},
    )
    session_store.finish_agent_run(run_id, "completed", output={"returned_count": 1})
    candidate_service.create_batch(
        "default",
        turn.turn_id,
        "graph reconstruction",
        [{"paper": _paper("candidate-paper"), "judgement": _judgement()}],
    )

    reset_script = _load_reset_script()
    counts = reset_script.reset_demo_session(str(database_path))

    assert counts == {
        "agent_runs": 1,
        "agent_contexts": 1,
        "candidate_items": 1,
        "candidate_batches": 1,
        "messages": 2,
        "conversation_turns": 1,
    }
    assert session_store.list_messages("default") == []
    assert candidate_service.list_active("default") == []
    assert session_store.get_agent_context("default", "research") == ""

    with sqlite3.connect(database_path) as connection:
        session = connection.execute(
            """
            SELECT summary, summary_through_message_id, status
            FROM sessions
            WHERE id = 'default'
            """
        ).fetchone()
        paper = connection.execute(
            "SELECT paper_id, status, pdf_path FROM papers WHERE paper_id = ?",
            (saved_paper.paper_id,),
        ).fetchone()
        knowledge_chunk_count = connection.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE paper_id = ?",
            (saved_paper.paper_id,),
        ).fetchone()[0]

    assert session == ("", None, "active")
    assert paper == ("saved-paper", "embedded", "/tmp/saved-paper.pdf")
    assert knowledge_chunk_count == 1

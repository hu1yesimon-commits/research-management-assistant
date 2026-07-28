#!/usr/bin/env python3
"""Seed contract-driven demo data for Agent Team V3.

This prepares stable local data for explaining the non-LLM default path:
- structured experiment logs used as episodic memory
- confirmed semantic memory used by deterministic query rewriting
- one saved/embedded paper metadata record with local knowledge chunks

The default fake vector store is in-memory, so this script does not make
retrieval evidence available across backend processes by itself. It does make
the SQLite-side contract data visible to memory context, saved papers, and docs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from services.memory_store import MemoryStore
from services.schemas import JudgeResult, PaperId, PaperMetadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-path",
        default="backend/data/manual-test.sqlite3",
        help="SQLite database path to seed.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    database_path = Path(args.database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    store = MemoryStore(str(database_path))
    store.initialize()

    log_ids = seed_experiment_logs(store)
    memory_id = seed_semantic_memory(store, log_ids)
    paper_id = seed_embedded_paper(store)

    print(f"DEMO_DATABASE_PATH={database_path}")
    print(f"SEEDED_EXPERIMENT_LOG_IDS={','.join(str(log_id) for log_id in log_ids)}")
    print(f"SEEDED_SEMANTIC_MEMORY_ID={memory_id}")
    print(f"SEEDED_EMBEDDED_PAPER_ID={paper_id}")
    print("CONTRACT_DEMO_SEED_OK=true")


def seed_experiment_logs(store: MemoryStore) -> list[int]:
    entries = [
        {
            "task": "1D time series classification",
            "model": "1D-CNN",
            "dataset": "bearing fault vibration dataset",
            "metric_problem": "minority class PRAUC is low and precision collapses",
            "tried_methods": ["class weighting", "focal loss"],
            "observation": "recall improves after focal loss but false positives increase",
            "goal": "improve minority-class PRAUC without making the model too heavy",
            "tags": ["imbalanced-learning", "lightweight", "loss"],
        },
        {
            "task": "graph reconstruction",
            "model": "GNN baseline",
            "dataset": "synthetic sparse graphs",
            "metric_problem": "thin-edge recall is unstable",
            "tried_methods": ["threshold tuning", "message passing depth sweep"],
            "observation": "deeper models recover dense regions but miss thin structures",
            "goal": "improve thin-edge recall while keeping inference lightweight",
            "tags": ["graph-reconstruction", "lightweight", "interpretability"],
        },
    ]
    return [store.add_experiment_log_entry(entry) for entry in entries]


def seed_semantic_memory(store: MemoryStore, log_ids: list[int]) -> int:
    return store.upsert_semantic_memory_from_candidate(
        {
            "category": "research_topic",
            "subject": "1D time series classification",
            "predicate": "needs",
            "object": "lightweight interpretable imbalance handling",
            "summary": (
                "The current demo project needs lightweight, interpretable methods "
                "for imbalanced 1D time-series classification; prior logs mention "
                "focal loss, class weighting, precision collapse, and PRAUC."
            ),
            "score": 0.92,
            "evidence_count": len(log_ids),
            "source_log_ids": log_ids,
        }
    )


def seed_embedded_paper(store: MemoryStore) -> str:
    paper = PaperMetadata(
        paper_id="demo-imbalanced-time-series",
        source_ids=PaperId(doi="10.1000/demo-imbalanced-time-series"),
        title="Precision-Recall Evaluation for Imbalanced Time-Series Classification",
        authors=["Demo Researcher"],
        abstract=(
            "A local demo paper about using precision-recall metrics, calibration, "
            "and loss-function comparisons for imbalanced time-series classifiers."
        ),
        doi="10.1000/demo-imbalanced-time-series",
        source="demo",
    )
    judgement = JudgeResult(
        decision="accept",
        reason="Demo evidence for contract-driven Idea Agent behavior.",
        llm_relevance_score=0.9,
        embedding_relevance_score=0.85,
        quality_score=0.8,
        novelty_score=0.7,
        final_score=0.83,
        tags=["demo", "imbalanced-learning", "time-series"],
    )
    store.save_candidate_paper(paper, judgement)
    store.update_paper_status(
        paper.paper_id,
        "embedded",
        pdf_path="/demo/precision-recall-time-series.pdf",
    )
    store.delete_knowledge_chunks_by_paper(paper.paper_id)
    store.insert_knowledge_chunks(
        paper.paper_id,
        [
            {
                "chunk_index": 0,
                "text": (
                    "Precision-recall metrics are more informative than accuracy "
                    "for imbalanced time-series classification."
                ),
                "chunk_hash": "demo-hash-0",
                "vector_ref": "chroma:research_chunks:demo-imbalanced-time-series:0:demo-hash-0",
            },
            {
                "chunk_index": 1,
                "text": (
                    "Calibration and threshold tuning can improve operating-point "
                    "selection without increasing 1D-CNN model size."
                ),
                "chunk_hash": "demo-hash-1",
                "vector_ref": "chroma:research_chunks:demo-imbalanced-time-series:1:demo-hash-1",
            },
        ],
    )
    return paper.paper_id


if __name__ == "__main__":
    main()

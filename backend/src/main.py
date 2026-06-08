from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile

from config import config
from graph.builder import build_paper_discovery_graph
from services.knowledge_base import KnowledgeBase
from services.memory_store import MemoryStore
from services.schemas import LogRequest, PaperStatus, SearchRequest


app = FastAPI(title="Research Management MVP")


def get_memory_store(database_path: str | None = None) -> MemoryStore:
    store = MemoryStore(database_path or config.database_path)
    store.initialize()
    return store


def get_paper_discovery_graph(store: MemoryStore = Depends(get_memory_store)):
    return build_paper_discovery_graph(memory_store=store)


def get_knowledge_base(upload_dir: str | None = None) -> KnowledgeBase:
    return KnowledgeBase(upload_dir or config.pdf_upload_dir)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/search")
def search(
    request: SearchRequest,
    graph=Depends(get_paper_discovery_graph),
):
    result = graph.invoke(
        {
            "mode": request.mode,
            "user_query": request.query,
            "memory_context": "",
            "rewritten_queries": [],
            "raw_results": [],
            "normalized_papers": [],
            "deduped_papers": [],
            "judge_results": [],
            "ranked_candidates": [],
        }
    )
    return result["ranked_candidates"]


@app.get("/papers/candidates")
def list_candidates(store: MemoryStore = Depends(get_memory_store)):
    return store.list_candidate_papers()


@app.post("/papers/{paper_id}/accept")
def accept_paper(
    paper_id: str,
    store: MemoryStore = Depends(get_memory_store),
):
    if store.get_paper(paper_id) is None:
        raise HTTPException(status_code=404, detail=f"paper not found: {paper_id}")

    store.update_paper_status(paper_id, PaperStatus.accepted.value)
    return {"paper_id": paper_id, "status": PaperStatus.accepted.value}


@app.post("/papers/{paper_id}/upload_pdf")
async def upload_pdf(
    paper_id: str,
    file: UploadFile = File(...),
    store: MemoryStore = Depends(get_memory_store),
    knowledge_base: KnowledgeBase = Depends(get_knowledge_base),
):
    if store.get_paper(paper_id) is None:
        raise HTTPException(status_code=404, detail=f"paper not found: {paper_id}")

    content = await file.read()
    pdf_path = knowledge_base.save_pdf(
        paper_id=paper_id,
        filename=file.filename or f"{paper_id}.pdf",
        content=content,
    )
    store.update_paper_status(paper_id, "uploaded", pdf_path=pdf_path)
    return {"paper_id": paper_id, "status": "uploaded", "pdf_path": pdf_path}


@app.post("/papers/{paper_id}/embed")
def embed_paper(
    paper_id: str,
    store: MemoryStore = Depends(get_memory_store),
    knowledge_base: KnowledgeBase = Depends(get_knowledge_base),
):
    paper = store.get_paper(paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"paper not found: {paper_id}")
    if paper["status"] != PaperStatus.uploaded.value:
        raise HTTPException(status_code=400, detail=f"paper is not uploaded: {paper_id}")
    if not paper["pdf_path"]:
        raise HTTPException(status_code=400, detail=f"paper pdf_path missing: {paper_id}")
    if not Path(paper["pdf_path"]).exists():
        raise HTTPException(status_code=400, detail=f"paper pdf_path does not exist: {paper['pdf_path']}")

    try:
        text = knowledge_base.extract_text(paper["pdf_path"])
        chunks = knowledge_base.chunk_text(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not chunks:
        raise HTTPException(status_code=400, detail=f"no chunks produced for paper: {paper_id}")

    store.delete_knowledge_chunks_by_paper(paper_id)
    store.insert_knowledge_chunks(paper_id, chunks)
    store.update_paper_status(paper_id, PaperStatus.chunked.value)
    return {
        "paper_id": paper_id,
        "status": PaperStatus.chunked.value,
        "pdf_path": paper["pdf_path"],
        "chunk_count": len(chunks),
    }


@app.post("/logs")
def add_log(request: LogRequest, store: MemoryStore = Depends(get_memory_store)):
    log_id = store.add_experiment_log(request.content, request.tags)
    return {"id": log_id}


@app.get("/logs")
def list_logs(store: MemoryStore = Depends(get_memory_store)):
    return store.list_experiment_logs()


@app.get("/memory/summary")
def memory_summary(store: MemoryStore = Depends(get_memory_store)):
    candidates = store.list_candidate_papers()
    return {
        "candidate_count": len(candidates),
        "known_dois": store.list_known_dois(),
        "recent_logs": store.list_experiment_logs(limit=5),
    }

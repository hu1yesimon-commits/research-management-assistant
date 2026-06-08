from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from langchain_openai import ChatOpenAI

from config import config
from graph.builder import build_paper_discovery_graph
from services.answer_service import AnswerGenerator, FakeGroundedAnswerGenerator, LLMAnswerGenerator, PromptBuilder
from services.embedding_pipeline import EmbeddingPipelineError, EmbeddingPipelineService
from services.embedding_service import BgeM3EmbeddingService, EmbeddingService, FakeEmbeddingService
from services.knowledge_base import KnowledgeBase
from services.memory_store import MemoryStore
from services.qa_service import KnowledgeQAService, QAServiceError
from services.retrieval_service import KnowledgeRetrievalService, RetrievalServiceError
from services.schemas import KnowledgeAnswerRequest, KnowledgeSearchRequest, LogRequest, PaperStatus, SearchRequest
from services.vector_store import ChromaVectorStoreService, FakeVectorStoreService, VectorStoreService


app = FastAPI(title="Research Management MVP")


def get_memory_store(database_path: str | None = None) -> MemoryStore:
    store = MemoryStore(database_path or config.database_path)
    store.initialize()
    return store


def get_paper_discovery_graph(store: MemoryStore = Depends(get_memory_store)):
    return build_paper_discovery_graph(memory_store=store)


def get_knowledge_base(upload_dir: str | None = None) -> KnowledgeBase:
    return KnowledgeBase(upload_dir or config.pdf_upload_dir)


def get_embedding_service() -> EmbeddingService:
    if config.embedding_provider == "bge-m3":
        return BgeM3EmbeddingService(model_name=config.bge_m3_model_name)
    return FakeEmbeddingService()


def get_vector_store_service() -> VectorStoreService:
    if config.vector_backend == "chroma":
        return ChromaVectorStoreService(
            persist_dir=config.chroma_persist_dir,
            collection_name=config.chroma_collection_name,
        )
    return FakeVectorStoreService(collection_name=config.chroma_collection_name)


def get_answer_generator() -> AnswerGenerator:
    if config.answer_provider == "deterministic":
        return FakeGroundedAnswerGenerator()
    if config.answer_provider == "openai":
        return LLMAnswerGenerator(
            llm_client=ChatOpenAI(
                model=config.answer_model,
                temperature=config.answer_temperature,
            ),
            prompt_builder=PromptBuilder(),
        )
    raise ValueError(f"unsupported ANSWER_PROVIDER: {config.answer_provider}")


def get_answer_mode() -> str:
    if config.answer_provider == "deterministic":
        return "deterministic"
    return "llm"


def get_embedding_pipeline_service(
    store: MemoryStore = Depends(get_memory_store),
    knowledge_base: KnowledgeBase = Depends(get_knowledge_base),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    vector_store_service: VectorStoreService = Depends(get_vector_store_service),
) -> EmbeddingPipelineService:
    return EmbeddingPipelineService(
        store=store,
        knowledge_base=knowledge_base,
        embedding_service=embedding_service,
        vector_store_service=vector_store_service,
    )


def get_knowledge_retrieval_service(
    store: MemoryStore = Depends(get_memory_store),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    vector_store_service: VectorStoreService = Depends(get_vector_store_service),
) -> KnowledgeRetrievalService:
    return KnowledgeRetrievalService(
        store=store,
        embedding_service=embedding_service,
        vector_store_service=vector_store_service,
    )


def get_knowledge_qa_service(
    retrieval_service: KnowledgeRetrievalService = Depends(get_knowledge_retrieval_service),
    answer_generator: AnswerGenerator = Depends(get_answer_generator),
) -> KnowledgeQAService:
    return KnowledgeQAService(
        retrieval_service=retrieval_service,
        answer_generator=answer_generator,
        mode=get_answer_mode(),
    )


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
    pipeline: EmbeddingPipelineService = Depends(get_embedding_pipeline_service),
):
    try:
        return pipeline.run(paper_id)
    except EmbeddingPipelineError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/knowledge/search")
def knowledge_search(
    request: KnowledgeSearchRequest,
    retrieval_service: KnowledgeRetrievalService = Depends(get_knowledge_retrieval_service),
):
    try:
        return retrieval_service.search(request.query, top_k=request.top_k)
    except RetrievalServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/knowledge/answer")
def knowledge_answer(
    request: KnowledgeAnswerRequest,
    qa_service: KnowledgeQAService = Depends(get_knowledge_qa_service),
):
    try:
        return qa_service.answer(request.question, top_k=request.top_k)
    except QAServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


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

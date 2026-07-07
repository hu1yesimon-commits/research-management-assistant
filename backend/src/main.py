from functools import lru_cache

from fastapi import Body, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langchain_openai import ChatOpenAI

from agent_team.dispatcher import DirectAgentDispatcher
from agent_team.idea_agent import IdeaAgent
from agent_team.providers import build_leader_planner, build_leader_responder, build_summary_generator
from agent_team.research_agent import ResearchAgent
from agent_team.validator import PlanValidator
from config import config
from graph.builder import build_paper_discovery_graph
from services.answer_service import AnswerGenerator, FakeGroundedAnswerGenerator, LLMAnswerGenerator, PromptBuilder
from services.candidate_lifecycle import (
    CandidateExpiredError,
    CandidateLifecycleService,
    CandidateNotFoundError,
)
from services.conversation_service import ConversationService
from services.embedding_pipeline import EmbeddingPipelineError, EmbeddingPipelineService
from services.embedding_service import BgeM3EmbeddingService, EmbeddingService, FakeEmbeddingService
from services.idea_service import DeterministicIdeaGenerator, IdeaGenerator, IdeaRecommendationService, IdeaServiceError
from services.knowledge_base import KnowledgeBase
from services.LlmPaperSelect import LLMJudge
from services.memory_extractor import MemoryExtractor
from services.memory_service import MemoryService, MemoryServiceError
from services.memory_store import MemoryStore
from services.qa_service import KnowledgeQAService, QAServiceError
from services.research_assistant_workflow import ResearchAssistantWorkflowError, ResearchAssistantWorkflowService
from services.research_workflow import ResearchWorkflowError, ResearchWorkflowService
from services.retrieval_service import KnowledgeRetrievalService, RetrievalServiceError
from services.session_context import SessionContextBuilder, SessionSummaryService
from services.session_schemas import (
    CandidateAcceptResponse,
    MessagePage,
    SavedPaper,
    SessionCandidate,
    SessionTurnRequest,
    SessionTurnResponse,
)
from services.session_store import SessionBusyError, SessionStore
from services.schemas import (
    AcceptPaperRequest,
    ExperimentLogCreateResponse,
    ExperimentLogEntry,
    ExperimentLogRequest,
    IdeaRecommendRequest,
    KnowledgeAnswerRequest,
    KnowledgeSearchRequest,
    LogRequest,
    MemoryCandidate,
    PaperStatus,
    ResearchAssistantRequest,
    ResearchAssistantResponse,
    ResearchQueryRequest,
    SearchRequest,
    SemanticMemoryEntry,
)
from services.vector_store import ChromaVectorStoreService, FakeVectorStoreService, VectorStoreService


app = FastAPI(title="Research Management MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=16)
def _get_cached_chroma_vector_store_service(
    vector_backend: str,
    chroma_persist_dir: str,
    chroma_collection_name: str,
) -> VectorStoreService:
    if vector_backend != "chroma":
        raise ValueError(f"unsupported cached vector backend: {vector_backend}")
    return ChromaVectorStoreService(
        persist_dir=chroma_persist_dir,
        collection_name=chroma_collection_name,
    )


def reset_vector_store_service_cache() -> None:
    _get_cached_chroma_vector_store_service.cache_clear()


@lru_cache(maxsize=8)
def _get_cached_embedding_service(
    embedding_provider: str,
    bge_m3_model_name: str,
) -> EmbeddingService:
    if embedding_provider != "bge-m3":
        raise ValueError(f"unsupported cached embedding provider: {embedding_provider}")
    return BgeM3EmbeddingService(model_name=bge_m3_model_name)


def reset_embedding_service_cache() -> None:
    _get_cached_embedding_service.cache_clear()


def create_memory_store(database_path: str) -> MemoryStore:
    store = MemoryStore(database_path)
    store.initialize()
    return store


def get_memory_store() -> MemoryStore:
    return create_memory_store(config.database_path)


def get_memory_service(store: MemoryStore = Depends(get_memory_store)) -> MemoryService:
    return MemoryService(store=store, extractor=MemoryExtractor())


def get_session_store() -> SessionStore:
    MemoryStore(config.database_path).initialize()
    return SessionStore(config.database_path)


def get_candidate_lifecycle_service() -> CandidateLifecycleService:
    MemoryStore(config.database_path).initialize()
    return CandidateLifecycleService(config.database_path)


def get_paper_judge() -> LLMJudge:
    if config.paper_judge_provider == "mock":
        return LLMJudge(provider_name="mock")
    if config.paper_judge_provider == "deepseek":
        return LLMJudge(
            provider_name="deepseek",
            llm_client=ChatOpenAI(
                model=config.paper_judge_model,
                temperature=0.0,
                api_key=config.deepseek_api_key,
                base_url=config.deepseek_base_url,
            ),
            model=config.paper_judge_model,
        )
    raise ValueError(f"unsupported PAPER_JUDGE_PROVIDER: {config.paper_judge_provider}")


def get_paper_discovery_graph(
    store: MemoryStore = Depends(get_memory_store),
    judge: LLMJudge = Depends(get_paper_judge),
):
    return build_paper_discovery_graph(memory_store=store, judge=judge)


def get_knowledge_base(upload_dir: str | None = None) -> KnowledgeBase:
    return KnowledgeBase(upload_dir or config.pdf_upload_dir)


def get_embedding_service() -> EmbeddingService:
    if config.embedding_provider == "bge-m3":
        return _get_cached_embedding_service(
            embedding_provider=config.embedding_provider,
            bge_m3_model_name=config.bge_m3_model_name,
        )
    return FakeEmbeddingService()


def get_vector_store_service() -> VectorStoreService:
    if config.vector_backend == "chroma":
        return _get_cached_chroma_vector_store_service(
            vector_backend=config.vector_backend,
            chroma_persist_dir=config.chroma_persist_dir,
            chroma_collection_name=config.chroma_collection_name,
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
    if config.answer_provider == "deepseek":
        return LLMAnswerGenerator(
            llm_client=ChatOpenAI(
                model=config.deepseek_model,
                temperature=config.answer_temperature,
                api_key=config.deepseek_api_key,
                base_url=config.deepseek_base_url,
            ),
            prompt_builder=PromptBuilder(),
        )
    raise ValueError(f"unsupported ANSWER_PROVIDER: {config.answer_provider}")


def get_answer_mode() -> str:
    if config.answer_provider == "deterministic":
        return "deterministic"
    return "llm"


def get_idea_generator() -> IdeaGenerator:
    if config.idea_provider == "deterministic":
        return DeterministicIdeaGenerator()
    raise ValueError(f"unsupported IDEA_PROVIDER: {config.idea_provider}")


def get_idea_mode() -> str:
    return config.idea_provider


def get_idea_recommendation_service(
    store: MemoryStore = Depends(get_memory_store),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    vector_store_service: VectorStoreService = Depends(get_vector_store_service),
    idea_generator: IdeaGenerator = Depends(get_idea_generator),
    discovery_graph=Depends(get_paper_discovery_graph),
) -> IdeaRecommendationService:
    retrieval_service = KnowledgeRetrievalService(
        store=store,
        embedding_service=embedding_service,
        vector_store_service=vector_store_service,
    )
    return IdeaRecommendationService(
        store=store,
        retrieval_service=retrieval_service,
        idea_generator=idea_generator,
        discovery_graph=discovery_graph,
        mode=get_idea_mode(),
    )


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


def get_research_workflow_service(
    discovery_graph=Depends(get_paper_discovery_graph),
    qa_service: KnowledgeQAService = Depends(get_knowledge_qa_service),
) -> ResearchWorkflowService:
    return ResearchWorkflowService(
        discovery_graph=discovery_graph,
        knowledge_qa_service=qa_service,
    )


def get_research_assistant_workflow_service(
    store: MemoryStore = Depends(get_memory_store),
    discovery_graph=Depends(get_paper_discovery_graph),
    qa_service: KnowledgeQAService = Depends(get_knowledge_qa_service),
    idea_service: IdeaRecommendationService = Depends(get_idea_recommendation_service),
) -> ResearchAssistantWorkflowService:
    return ResearchAssistantWorkflowService(
        store=store,
        discovery_graph=discovery_graph,
        knowledge_qa_service=qa_service,
        idea_service=idea_service,
    )


def get_session_context_builder(
    session_store: SessionStore = Depends(get_session_store),
    memory_store: MemoryStore = Depends(get_memory_store),
) -> SessionContextBuilder:
    return SessionContextBuilder(session_store=session_store, memory_store=memory_store)


def get_session_summary_service(
    session_store: SessionStore = Depends(get_session_store),
) -> SessionSummaryService:
    return SessionSummaryService(
        session_store=session_store,
        generator=build_summary_generator(config),
    )


def get_leader_planner():
    return build_leader_planner(config)


def get_leader_responder():
    return build_leader_responder(config)


def get_research_agent(
    discovery_graph=Depends(get_paper_discovery_graph),
    candidate_service: CandidateLifecycleService = Depends(get_candidate_lifecycle_service),
) -> ResearchAgent:
    return ResearchAgent(
        discovery_graph=discovery_graph,
        candidate_service=candidate_service,
    )


def get_idea_agent(
    idea_service: IdeaRecommendationService = Depends(get_idea_recommendation_service),
) -> IdeaAgent:
    return IdeaAgent(idea_service=idea_service)


def get_direct_agent_dispatcher(
    knowledge_service: KnowledgeQAService = Depends(get_knowledge_qa_service),
    research_agent: ResearchAgent = Depends(get_research_agent),
    idea_agent: IdeaAgent = Depends(get_idea_agent),
    session_store: SessionStore = Depends(get_session_store),
) -> DirectAgentDispatcher:
    return DirectAgentDispatcher(
        knowledge_service=knowledge_service,
        research_agent=research_agent,
        idea_agent=idea_agent,
        session_store=session_store,
        agent_step_timeout_seconds=config.agent_step_timeout_seconds,
    )


def get_conversation_service(
    session_store: SessionStore = Depends(get_session_store),
    candidate_service: CandidateLifecycleService = Depends(get_candidate_lifecycle_service),
    context_builder: SessionContextBuilder = Depends(get_session_context_builder),
    knowledge_retrieval: KnowledgeRetrievalService = Depends(get_knowledge_retrieval_service),
    planner=Depends(get_leader_planner),
    dispatcher: DirectAgentDispatcher = Depends(get_direct_agent_dispatcher),
    responder=Depends(get_leader_responder),
    summary_service: SessionSummaryService = Depends(get_session_summary_service),
) -> ConversationService:
    return ConversationService(
        store=session_store,
        candidate_service=candidate_service,
        context_builder=context_builder,
        knowledge_retrieval=knowledge_retrieval,
        planner=planner,
        validator=PlanValidator(),
        dispatcher=dispatcher,
        responder=responder,
        summary_service=summary_service,
        turn_timeout_seconds=config.turn_timeout_seconds,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _require_default_session(session_id: str) -> None:
    if session_id != "default":
        raise HTTPException(status_code=404, detail="Session not found")


@app.post("/sessions/{session_id}/turns", response_model=SessionTurnResponse)
def create_session_turn(
    session_id: str,
    request: SessionTurnRequest,
    service: ConversationService = Depends(get_conversation_service),
):
    _require_default_session(session_id)
    try:
        return service.run(session_id, request)
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/sessions/{session_id}/messages", response_model=MessagePage)
def list_session_messages(
    session_id: str,
    before_id: int | None = None,
    limit: int = 50,
    store: SessionStore = Depends(get_session_store),
):
    _require_default_session(session_id)
    bounded_limit = min(max(limit, 1), 100)
    messages = store.list_messages(
        session_id,
        before_id=before_id,
        limit=bounded_limit + 1,
    )
    has_more = len(messages) > bounded_limit
    items = messages[-bounded_limit:]
    return MessagePage(
        items=items,
        next_before_id=items[0].id if has_more and items else None,
    )


@app.get(
    "/sessions/{session_id}/candidates/active",
    response_model=list[SessionCandidate],
)
def list_active_candidates(
    session_id: str,
    service: CandidateLifecycleService = Depends(get_candidate_lifecycle_service),
):
    _require_default_session(session_id)
    return service.list_active(session_id)


@app.post(
    "/sessions/{session_id}/candidates/{candidate_id}/accept",
    response_model=CandidateAcceptResponse,
)
def accept_session_candidate(
    session_id: str,
    candidate_id: str,
    service: CandidateLifecycleService = Depends(get_candidate_lifecycle_service),
):
    _require_default_session(session_id)
    try:
        return service.accept(session_id, candidate_id)
    except CandidateExpiredError as exc:
        raise HTTPException(status_code=409, detail="Candidate expired") from exc
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/papers", response_model=list[SavedPaper])
def list_saved_papers(store: MemoryStore = Depends(get_memory_store)):
    return store.list_saved_papers()


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


@app.get(
    "/papers/candidates",
    deprecated=True,
    description="Deprecated: use session-scoped active candidate endpoints.",
)
def list_candidates(store: MemoryStore = Depends(get_memory_store)):
    return store.list_candidate_papers()


@app.post(
    "/papers/{paper_id}/accept",
    deprecated=True,
    description="Deprecated: use the session-scoped candidate accept endpoint.",
)
def accept_paper(
    paper_id: str,
    payload: AcceptPaperRequest | None = Body(default=None),
    store: MemoryStore = Depends(get_memory_store),
):
    existing = store.get_paper(paper_id)

    if existing is None:
        if payload is None or payload.paper is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"paper not found: {paper_id}; paper metadata is required to save a new discovery candidate. "
                    "Provide paper and optional judgement payload."
                ),
            )
        if payload.paper.paper_id != paper_id:
            raise HTTPException(
                status_code=400,
                detail=f"paper_id mismatch: path={paper_id} body={payload.paper.paper_id}",
            )
        store.save_candidate_paper(payload.paper, payload.judgement)

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


@app.post("/research/query")
def research_query(
    request: ResearchQueryRequest,
    workflow_service: ResearchWorkflowService = Depends(get_research_workflow_service),
):
    try:
        return workflow_service.query(
            query=request.query,
            mode=request.mode,
            include_discovery=request.include_discovery,
            include_knowledge=request.include_knowledge,
            top_k=request.top_k,
        )
    except ResearchWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/research/assistant", response_model=ResearchAssistantResponse)
def research_assistant(
    request: ResearchAssistantRequest,
    workflow_service: ResearchAssistantWorkflowService = Depends(get_research_assistant_workflow_service),
):
    try:
        return workflow_service.query(
            query=request.query,
            intent=request.intent,
            experiment_log=request.experiment_log,
            top_k=request.top_k,
            idea_count=request.idea_count,
            save_log=request.save_log,
            include_discovery=request.include_discovery,
        )
    except ResearchAssistantWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/logs")
def add_log(request: LogRequest, store: MemoryStore = Depends(get_memory_store)):
    log_id = store.add_experiment_log(request.content, request.tags)
    return {"id": log_id}


@app.get("/logs")
def list_logs(store: MemoryStore = Depends(get_memory_store)):
    return store.list_experiment_logs()


@app.post("/experiments/logs", response_model=ExperimentLogCreateResponse)
def add_experiment_log_entry(
    request: ExperimentLogRequest,
    store: MemoryStore = Depends(get_memory_store),
):
    log_id = store.add_experiment_log_entry(request.model_dump())
    entry = store.list_experiment_log_entries(limit=1)[0]
    return ExperimentLogCreateResponse(id=log_id, created_at=entry["created_at"])


@app.get("/experiments/logs", response_model=list[ExperimentLogEntry])
def list_experiment_log_entries(store: MemoryStore = Depends(get_memory_store)):
    return store.list_experiment_log_entries()


@app.post("/ideas/recommend")
def recommend_ideas(
    request: IdeaRecommendRequest,
    service: IdeaRecommendationService = Depends(get_idea_recommendation_service),
):
    try:
        return service.recommend(
            experiment_log=request.experiment_log,
            save_log=request.save_log,
            include_discovery=request.include_discovery,
            top_k=request.top_k,
            idea_count=request.idea_count,
        )
    except IdeaServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/memory/candidates", response_model=list[MemoryCandidate])
def list_memory_candidates(
    status: str = "pending",
    candidate_type: str | None = None,
    category: str | None = None,
    store: MemoryStore = Depends(get_memory_store),
):
    return store.list_memory_candidates(
        status=status,
        candidate_type=candidate_type,
        category=category,
    )


@app.post("/memory/candidates/refresh", response_model=list[MemoryCandidate])
def refresh_memory_candidates(service: MemoryService = Depends(get_memory_service)):
    return service.refresh_candidates()


@app.post("/memory/candidates/{candidate_id}/accept", response_model=SemanticMemoryEntry)
def accept_memory_candidate(
    candidate_id: int,
    service: MemoryService = Depends(get_memory_service),
):
    try:
        return service.accept_candidate(candidate_id)
    except MemoryServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/memory/candidates/{candidate_id}/reject", response_model=MemoryCandidate)
def reject_memory_candidate(
    candidate_id: int,
    service: MemoryService = Depends(get_memory_service),
):
    try:
        return service.reject_candidate(candidate_id)
    except MemoryServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/memory/semantic", response_model=list[SemanticMemoryEntry])
def list_semantic_memory(
    status: str = "confirmed",
    category: str | None = None,
    predicate: str | None = None,
    store: MemoryStore = Depends(get_memory_store),
):
    return store.list_semantic_memory(
        status=status,
        category=category,
        predicate=predicate,
    )


@app.post("/memory/semantic/{memory_id}/archive", response_model=SemanticMemoryEntry)
def archive_semantic_memory(
    memory_id: int,
    service: MemoryService = Depends(get_memory_service),
):
    try:
        return service.archive_semantic_memory(memory_id)
    except MemoryServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/memory/summary")
def memory_summary(store: MemoryStore = Depends(get_memory_store)):
    saved_paper_count = store.count_candidate_papers()
    pending_candidates = store.list_memory_candidates(status="pending")
    confirmed_memories = store.list_semantic_memory(status="confirmed")
    known_dois = store.list_known_dois()
    return {
        "candidate_count": saved_paper_count,
        "saved_paper_count": saved_paper_count,
        "pending_candidate_count": len(pending_candidates),
        "confirmed_memory_count": len(confirmed_memories),
        "known_doi_count": len(known_dois),
        "recent_logs": store.list_experiment_logs(limit=5),
    }

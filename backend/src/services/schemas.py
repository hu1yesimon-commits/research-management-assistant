from enum import Enum
from pydantic import BaseModel, Field, model_validator
from typing import Literal

class PaperId(BaseModel):
    arxiv_id: str | None = None
    openalex_id: str | None = None
    semantic_scholar_id: str | None = None
    doi: str | None = None


"""
    有一个小提醒：PaperMetadata.fields_of_study 和 raw 仍然是可变默认值，
    虽然这次改了直接相关字段，但后续可以作为小型 cleanup 处理，不是当前阻塞。
"""

class PaperMetadata(BaseModel):
    paper_id: str                      # 内部唯一标识
    source_ids: PaperId              # 各个源的ID，至少一个非空，doi优先，其次 arxivid 和 openalex_id
    title: str 
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None 
    published_date: str | None = None
    venue: str | None = None
    venue_type: str | None = None
    doi: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    source: str                        # "arxiv" | "openalex" | "merged"
    citation_count: int | None = None
    is_open_access: bool | None = None 
    fields_of_study: list[str] = []  
    raw: dict = {} # 存储多个源获取的原始数据，方便后续调试和扩展



class JudgeResult(BaseModel):
    decision: Literal["accept", "reject", "uncertain"]  # 评审结果
    reason: str | None = None  # 评审理由，尤其在 reject 时很重要
    llm_relevance_score: float = Field(ge=0, le=1)  # LLM 判断这篇论文是否真正服务于当前 query / 项目目标，权重要略高于 embedding
    embedding_relevance_score: float = Field(ge=0, le=1)  # query 与 title + abstract 的向量相似度
    quality_score: float = Field(ge=0, le=1)  # LLM 根据 venue、citation_count、年份、source_ids、abstract 完整度等判断
    novelty_score: float = Field(ge=0, le=1)  # 规则函数计算，比如指数衰减，LLM 只读取这个结果，不负责拍脑袋给分
    final_score: float = Field(ge=0, le=1)
    tags: list[str] = Field(default_factory=list)  # 后面真实接 LLM 时，tags 可以让模型输出结构化结果


class SearchRequest(BaseModel):
    mode: Literal["basic", "advanced"] = "basic"
    query: str


class LogRequest(BaseModel):
    content: str
    tags: list[str] = Field(default_factory=list)


class ExperimentLogRequest(BaseModel):
    task: str = Field(min_length=1)
    model: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    metric_problem: str = Field(min_length=1)
    tried_methods: list[str] = Field(default_factory=list)
    observation: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class ExperimentLogEntry(ExperimentLogRequest):
    id: int
    created_at: str


class ExperimentLogCreateResponse(BaseModel):
    id: int
    created_at: str


class MemoryCategory(str, Enum):
    research_topic = "research_topic"
    experiment_target = "experiment_target"
    result_trend = "result_trend"
    recurring_block = "recurring_block"
    user_preference = "user_preference"


class MemoryPredicate(str, Enum):
    focuses_on = "focuses_on"
    uses_object = "uses_object"
    shows_trend = "shows_trend"
    blocked_by = "blocked_by"
    prefers = "prefers"
    avoids = "avoids"


class MemoryCandidateType(str, Enum):
    semantic_proposal = "semantic_proposal"
    stale_proposal = "stale_proposal"
    conflict_proposal = "conflict_proposal"


class MemoryCandidateStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    expired = "expired"


class SemanticMemoryStatus(str, Enum):
    confirmed = "confirmed"
    archived = "archived"


class MemoryCandidate(BaseModel):
    id: int
    candidate_type: MemoryCandidateType
    category: MemoryCategory
    subject: str
    predicate: MemoryPredicate
    object: str
    summary: str
    source_log_ids: list[int] = Field(default_factory=list)
    evidence_count: int
    score: float = Field(ge=0, le=1)
    status: MemoryCandidateStatus
    created_at: str
    reviewed_at: str | None = None


class SemanticMemoryEntry(BaseModel):
    id: int
    category: MemoryCategory
    subject: str
    predicate: MemoryPredicate
    object: str
    summary: str
    confidence: float = Field(ge=0, le=1)
    support_count: int
    supporting_log_ids: list[int] = Field(default_factory=list)
    status: SemanticMemoryStatus
    last_confirmed_at: str
    created_at: str
    updated_at: str


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchResult(BaseModel):
    paper_id: str
    chunk_index: int
    text: str
    vector_ref: str
    distance: float
    title: str | None = None


class KnowledgeSearchResponse(BaseModel):
    query: str
    top_k: int
    results: list[KnowledgeSearchResult] = Field(default_factory=list)


class KnowledgeAnswerRequest(BaseModel):
    question: str
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeAnswerSource(BaseModel):
    paper_id: str
    title: str | None = None
    chunk_index: int
    distance: float
    text: str
    vector_ref: str


class KnowledgeAnswerResponse(BaseModel):
    question: str
    answer: str
    sources: list[KnowledgeAnswerSource] = Field(default_factory=list)
    mode: str


class IdeaSupportingEvidence(BaseModel):
    source_type: Literal["knowledge", "discovery"]
    paper_id: str | None = None
    title: str | None = None
    chunk_index: int | None = None
    distance: float | None = None
    text: str | None = None
    vector_ref: str | None = None


class IdeaOption(BaseModel):
    title: str
    rationale: str
    supporting_evidence: list[IdeaSupportingEvidence] = Field(default_factory=list)
    expected_benefit: str
    risk: str
    suggested_validation_metric: str
    next_small_experiment: str


class IdeaKnowledgeSection(BaseModel):
    sources: list[KnowledgeAnswerSource] = Field(default_factory=list)
    error: str | None = None


class IdeaDiscoverySection(BaseModel):
    enabled: bool
    candidates: list[dict] = Field(default_factory=list)
    error: str | None = None


class IdeaRecommendRequest(BaseModel):
    experiment_log: ExperimentLogRequest
    save_log: bool = True
    include_discovery: bool = False
    top_k: int = Field(default=5, ge=1, le=20)
    idea_count: int = Field(default=3, ge=3, le=5)


class IdeaRecommendResponse(BaseModel):
    log_id: int | None = None
    query: str
    knowledge: IdeaKnowledgeSection
    discovery: IdeaDiscoverySection
    ideas: list[IdeaOption] = Field(default_factory=list)
    mode: str


class ResearchQueryRequest(BaseModel):
    query: str
    mode: Literal["basic", "advanced"] = "basic"
    include_discovery: bool = True
    include_knowledge: bool = True
    top_k: int = Field(default=5, ge=1, le=20)


class AcceptPaperRequest(BaseModel):
    paper: PaperMetadata | None = None
    judgement: JudgeResult | None = None


class ResearchDiscoverySection(BaseModel):
    enabled: bool
    candidates: list[dict] = Field(default_factory=list)
    error: str | None = None


class ResearchKnowledgeSection(BaseModel):
    enabled: bool
    answer: str | None = None
    sources: list[KnowledgeAnswerSource] = Field(default_factory=list)
    error: str | None = None
    mode: str | None = None


class ResearchQueryResponse(BaseModel):
    query: str
    mode: str
    discovery: ResearchDiscoverySection
    knowledge: ResearchKnowledgeSection


class AssistantStageError(BaseModel):
    stage: Literal[
        "coverage",
        "query_rewrite",
        "multi_search",
        "postprocess",
        "llm_judge",
        "rank",
        "knowledge_answer",
        "idea_generation",
        "routing",
    ]
    message: str
    recoverable: bool = True


class DiscoveryResult(BaseModel):
    enabled: bool
    top_k: list[dict] = Field(default_factory=list)
    rewritten_queries: list[str] = Field(default_factory=list)
    total_raw: int = 0
    total_deduped: int = 0
    scoring_summary: dict = Field(default_factory=dict)
    error: str | None = None


class KnowledgeResult(BaseModel):
    enabled: bool
    answer: str | None = None
    sources: list[KnowledgeAnswerSource] = Field(default_factory=list)
    mode: str | None = None
    error: str | None = None


class IdeaResult(BaseModel):
    enabled: bool
    ideas: list[IdeaOption] = Field(default_factory=list)
    supporting_evidence: list[IdeaSupportingEvidence] = Field(default_factory=list)
    log_id: int | None = None
    error: str | None = None


class NextActionOption(BaseModel):
    id: str
    label: str
    request_patch: dict = Field(default_factory=dict)


class ResearchAssistantNextAction(BaseModel):
    type: Literal["choose_path", "choose_intent", "upload_pdf", "select_idea", "none"]
    options: list[NextActionOption] = Field(default_factory=list)
    message: str | None = None


class ResearchAssistantError(AssistantStageError):
    section: Literal["coverage", "discovery", "knowledge", "idea", "routing"] | None = None

    @model_validator(mode="after")
    def populate_legacy_section(self):
        if self.section is not None:
            return self
        stage_to_section = {
            "coverage": "coverage",
            "query_rewrite": "discovery",
            "multi_search": "discovery",
            "postprocess": "discovery",
            "llm_judge": "discovery",
            "rank": "discovery",
            "knowledge_answer": "knowledge",
            "idea_generation": "idea",
            "routing": "routing",
        }
        self.section = stage_to_section[self.stage]
        return self


class ResearchAssistantRequest(BaseModel):
    query: str
    intent: Literal["auto", "search", "research"] = "auto"
    experiment_log: ExperimentLogRequest | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    idea_count: int = Field(default=3, ge=3, le=5)
    save_log: bool = True
    include_discovery: bool = False


class ResearchAssistantResponse(BaseModel):
    query: str
    intent: Literal["auto", "search", "research"]
    mode: Literal["basic", "advanced"]
    route: Literal["basic_explore", "advanced_ready", "advanced_search", "research_idea"]
    coverage_score: float = Field(ge=0, le=1)
    route_reason: str
    assistant_message: str
    next_action: ResearchAssistantNextAction | None = None
    suggested_user_actions: list[str] = Field(default_factory=list)
    discovery: ResearchDiscoverySection
    knowledge: ResearchKnowledgeSection
    ideas: list[IdeaOption] = Field(default_factory=list)
    discovery_result: DiscoveryResult = Field(default_factory=lambda: DiscoveryResult(enabled=False))
    knowledge_result: KnowledgeResult = Field(default_factory=lambda: KnowledgeResult(enabled=False))
    idea_result: IdeaResult = Field(default_factory=lambda: IdeaResult(enabled=False))
    errors: list[ResearchAssistantError] = Field(default_factory=list)


class PaperStatus(str, Enum):
    candidate = "candidate"
    accepted = "accepted"
    uploaded = "uploaded"
    chunked = "chunked"
    embedded = "embedded"
    rejected = "rejected"

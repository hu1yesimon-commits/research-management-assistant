from enum import Enum
from pydantic import BaseModel, Field
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


class PaperStatus(str, Enum):
    candidate = "candidate"
    accepted = "accepted"
    uploaded = "uploaded"
    chunked = "chunked"
    embedded = "embedded"
    rejected = "rejected"

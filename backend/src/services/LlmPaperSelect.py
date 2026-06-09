import json
import re
from dataclasses import dataclass, field

from services.schemas import JudgeResult, PaperMetadata
from services.scoreutils import ScoreUtils


@dataclass
class PaperJudgeProviderOutput:
    decision: str
    llm_relevance_score: float
    quality_score: float
    reason: str
    tags: list[str] = field(default_factory=list)


class MockPaperJudgeProvider:
    _TOP_VENUES = {
        "acl",
        "cvpr",
        "emnlp",
        "iclr",
        "icml",
        "kdd",
        "naacl",
        "nature",
        "neurips",
        "nips",
        "science",
        "www",
    }

    def evaluate(self, query: str, paper: PaperMetadata) -> PaperJudgeProviderOutput:
        llm_relevance_score = ScoreUtils.calculate_embedding_relevance_score(
            query=query,
            paper=paper,
        )
        quality_score = self._calculate_quality_score(paper)
        tags = self._build_tags(paper=paper, llm_relevance_score=llm_relevance_score)

        if llm_relevance_score >= 0.75 and quality_score >= 0.45:
            decision = "accept"
            reason = "Mock judge found strong query overlap and credible paper signals."
        elif llm_relevance_score < 0.25:
            decision = "reject"
            reason = "Mock judge found weak overlap with the user query."
        else:
            decision = "uncertain"
            reason = "Mock judge found partial relevance and suggests manual review."

        return PaperJudgeProviderOutput(
            decision=decision,
            llm_relevance_score=llm_relevance_score,
            quality_score=quality_score,
            reason=reason,
            tags=tags,
        )

    def _calculate_quality_score(self, paper: PaperMetadata) -> float:
        score = 0.0

        if paper.abstract:
            score += 0.30

        venue = (paper.venue or "").strip().lower()
        if venue:
            if venue in self._TOP_VENUES:
                score += 0.25
            else:
                score += 0.10

        citation_count = paper.citation_count or 0
        if citation_count >= 100:
            score += 0.25
        elif citation_count >= 20:
            score += 0.18
        elif citation_count > 0:
            score += 0.10

        identifier_count = sum(
            1
            for value in (
                paper.doi,
                paper.source_ids.openalex_id,
                paper.source_ids.arxiv_id,
                paper.source_ids.semantic_scholar_id,
            )
            if value
        )
        if identifier_count >= 2:
            score += 0.15
        elif identifier_count == 1:
            score += 0.10

        return round(min(score, 1.0), 4)

    def _build_tags(self, paper: PaperMetadata, llm_relevance_score: float) -> list[str]:
        tags = ["mock"]

        if llm_relevance_score >= 0.75:
            tags.append("high_query_overlap")
        elif llm_relevance_score > 0.0:
            tags.append("partial_query_overlap")
        else:
            tags.append("low_query_overlap")

        if (paper.citation_count or 0) >= 100:
            tags.append("high_citation")
        elif (paper.citation_count or 0) > 0:
            tags.append("has_citation")

        venue = (paper.venue or "").strip().lower()
        if venue in self._TOP_VENUES:
            tags.append("top_venue")
        elif venue:
            tags.append("has_venue")

        return tags


class DeepSeekPaperJudgeProvider:
    def __init__(self, llm_client: object, model: str):
        self._llm_client = llm_client
        self._model = model

    def evaluate(self, query: str, paper: PaperMetadata) -> PaperJudgeProviderOutput:
        prompt = self._build_prompt(query=query, paper=paper)
        response = self._llm_client.invoke(prompt)
        content = getattr(response, "content", response)
        payload = self._parse_json_payload(str(content))

        return PaperJudgeProviderOutput(
            decision=self._coerce_decision(payload.get("decision")),
            llm_relevance_score=self._coerce_score(payload.get("llm_relevance_score")),
            quality_score=self._coerce_score(payload.get("quality_score")),
            reason=str(payload.get("reason") or "").strip() or "DeepSeek provider returned no reason.",
            tags=self._coerce_tags(payload.get("tags")),
        )

    def _build_prompt(self, query: str, paper: PaperMetadata) -> str:
        paper_payload = {
            "query": query,
            "title": paper.title,
            "abstract": paper.abstract,
            "authors": paper.authors,
            "venue": paper.venue,
            "citation_count": paper.citation_count,
            "published_date": paper.published_date,
            "doi": paper.doi,
            "openalex_id": paper.source_ids.openalex_id,
        }
        paper_json = json.dumps(paper_payload, ensure_ascii=False, sort_keys=True)

        return (
            "You are a research paper judge.\n"
            "Read the query and paper metadata, then return only valid JSON.\n"
            "Do not add markdown fences or extra prose.\n"
            'JSON schema: {"decision":"accept|reject|uncertain","llm_relevance_score":0.0,'
            '"quality_score":0.0,"reason":"...","tags":["..."]}\n'
            "Scores must be in [0, 1]. Base relevance on query, title, abstract, and metadata.\n"
            "Base quality on venue, citation_count, metadata completeness, and paper credibility.\n"
            f"Model hint: {self._model}\n"
            f"Input: {paper_json}"
        )

    @staticmethod
    def _parse_json_payload(content: str) -> dict:
        candidate = content.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
            candidate = re.sub(r"\s*```$", "", candidate)

        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError(f"paper judge provider returned non-JSON content: {content}") from exc

        if not isinstance(payload, dict):
            raise ValueError("paper judge provider returned a non-object payload")
        return payload

    @staticmethod
    def _coerce_decision(value: object) -> str:
        if value in {"accept", "reject", "uncertain"}:
            return str(value)
        return "uncertain"

    @staticmethod
    def _coerce_score(value: object) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        return round(min(max(score, 0.0), 1.0), 4)

    @staticmethod
    def _coerce_tags(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]


class LLMJudge:
    def __init__(
        self,
        provider_name: str = "mock",
        llm_client: object | None = None,
        model: str = "",
        current_year: int = 2026,
    ):
        self.provider_name = provider_name
        self.llm_client = llm_client
        self.model = model
        self.current_year = current_year

        if provider_name == "mock":
            self._provider = MockPaperJudgeProvider()
        elif provider_name == "deepseek":
            if llm_client is None:
                raise ValueError("deepseek paper judge requires llm_client")
            self._provider = DeepSeekPaperJudgeProvider(llm_client=llm_client, model=model)
        else:
            raise ValueError(f"unsupported PAPER_JUDGE_PROVIDER: {provider_name}")

    def judge(self, query: str, paper: PaperMetadata) -> JudgeResult:
        novelty_score = ScoreUtils.calculate_novelty_score(
            paper,
            current_year=self.current_year,
        )

        if not paper.abstract:
            llm_relevance_score = 0.3
            embedding_relevance_score = 0.0
            quality_score = 0.3

            return JudgeResult(
                decision="uncertain",
                reason="缺少摘要，无法稳定判断。",
                llm_relevance_score=llm_relevance_score,
                embedding_relevance_score=embedding_relevance_score,
                quality_score=quality_score,
                novelty_score=novelty_score,
                final_score=ScoreUtils.calculate_final_score(
                    llm_relevance_score=llm_relevance_score,
                    embedding_relevance_score=embedding_relevance_score,
                    quality_score=quality_score,
                    novelty_score=novelty_score,
                ),
                tags=["missing_abstract", "needs_manual_review"],
            )

        provider_output = self._provider.evaluate(query=query, paper=paper)
        embedding_relevance_score = ScoreUtils.calculate_embedding_relevance_score(
            query=query,
            paper=paper,
        )

        return JudgeResult(
            decision=provider_output.decision,
            reason=provider_output.reason,
            llm_relevance_score=provider_output.llm_relevance_score,
            embedding_relevance_score=embedding_relevance_score,
            quality_score=provider_output.quality_score,
            novelty_score=novelty_score,
            final_score=ScoreUtils.calculate_final_score(
                llm_relevance_score=provider_output.llm_relevance_score,
                embedding_relevance_score=embedding_relevance_score,
                quality_score=provider_output.quality_score,
                novelty_score=novelty_score,
            ),
            tags=provider_output.tags,
        )

    def sort_by_final_score(self, results: list[JudgeResult]) -> list[JudgeResult]:
        return sorted(results, key=lambda result: result.final_score, reverse=True)

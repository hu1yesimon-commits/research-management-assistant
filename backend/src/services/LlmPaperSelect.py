from services.schemas import PaperMetadata, JudgeResult
from services.scoreutils import ScoreUtils

class LLMJudge:

    def judge(self, paper: PaperMetadata) -> JudgeResult:
        if not paper.abstract:
            llm_relevance_score = 0.3
            embedding_relevance_score = 0.0
            quality_score = 0.3
            novelty_score = 0.3

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

        llm_relevance_score = 0.7
        embedding_relevance_score = 0.65
        quality_score = 0.6
        novelty_score = 0.5

        return JudgeResult(
            decision="accept",
            reason="论文包含摘要，可进入后续 LLM 判断流程。",
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
            tags=["mock", "has_abstract"],
        )

    def sort_by_final_score(self, results: list[JudgeResult]) -> list[JudgeResult]:
        return sorted(results, key=lambda result: result.final_score, reverse=True)

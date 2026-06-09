import re

from services.schemas import PaperMetadata

class ScoreUtils:

    @staticmethod
    def calculate_final_score(
        llm_relevance_score: float,
        embedding_relevance_score: float,
        quality_score: float,
        novelty_score: float,
    ) -> float:
        return round(
            0.40 * llm_relevance_score
            + 0.15 * embedding_relevance_score
            + 0.25 * quality_score
            + 0.20 * novelty_score,
            4,
        )

    @staticmethod
    def calculate_embedding_relevance_score(query: str, paper: PaperMetadata) -> float:
        query_tokens = ScoreUtils._tokenize(query)
        if not query_tokens:
            return 0.0

        paper_text = " ".join(
            part
            for part in [
                paper.title,
                paper.abstract or "",
                paper.venue or "",
                " ".join(paper.authors),
            ]
            if part
        )
        paper_tokens = ScoreUtils._tokenize(paper_text)
        if not paper_tokens:
            return 0.0

        overlap = len(query_tokens & paper_tokens)
        return round(overlap / len(query_tokens), 4)

    @staticmethod
    def calculate_novelty_score(paper: PaperMetadata, current_year: int = 2026) -> float:
        if not paper.published_date:
            return 0.5

        try:
            published_year = int(paper.published_date[:4])
        except ValueError:
            return 0.5

        age = current_year - published_year
        if age < 0:
            return 0.5
        elif age == 0:
            return 1.0
        elif age <= 2:
            return round(1.0 - (age * 0.15), 4)
        else:
            return round(max(0.1, 1.0 - (age * 0.15)), 4)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if len(token) >= 2
        }

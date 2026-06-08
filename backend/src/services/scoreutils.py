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
            0.35 * llm_relevance_score
            + 0.20 * embedding_relevance_score
            + 0.25 * quality_score
            + 0.20 * novelty_score,
            4,
        )


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

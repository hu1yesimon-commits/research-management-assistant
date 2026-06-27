from typing import Literal


DiscoveryStage = Literal["query_rewrite", "multi_search", "postprocess", "llm_judge", "rank"]
DISCOVERY_STAGES = frozenset({"query_rewrite", "multi_search", "postprocess", "llm_judge", "rank"})


class DiscoveryStageError(Exception):
    def __init__(self, stage: DiscoveryStage, detail: str, recoverable: bool):
        if stage not in DISCOVERY_STAGES:
            raise ValueError(f"unsupported discovery stage: {stage}")
        super().__init__(detail)
        self.stage = stage
        self.detail = detail
        self.recoverable = recoverable

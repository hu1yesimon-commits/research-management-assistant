from services.LlmPaperSelect import LLMJudge
from services.deduplicator import DeDuplicator
from services.memory_store import MemoryStore
from services.paper_search import PaperSearchService
from services.query_rewriter import QueryRewriter
from graph.state import PaperDiscoveryState, PaperSelectState


def make_nodes(
    search_service: PaperSearchService,
    judge: LLMJudge,
    memory_store: MemoryStore,
    query_rewriter: QueryRewriter,
):
    def load_memory_context(state: PaperDiscoveryState) -> dict:
        return {"memory_context": memory_store.build_memory_context()}

    def rewrite_query(state: PaperDiscoveryState) -> dict:
        return {
            "rewritten_queries": query_rewriter.rewrite(
                mode=state["mode"],
                user_query=state["user_query"],
                memory_context=state["memory_context"],
            )
        }

    def multi_source_search(state: PaperDiscoveryState) -> dict:
        papers = []
        for query in state["rewritten_queries"]:
            papers.extend(search_service.search(query))
        return {"raw_results": papers, "normalized_papers": papers}

    def dedup_papers(state: PaperDiscoveryState) -> dict:
        deduplicator = DeDuplicator(known_dois=memory_store.list_known_dois())
        return {"deduped_papers": deduplicator.dedup(state["normalized_papers"])}

    def judge_papers(state: PaperDiscoveryState) -> dict:
        return {"judge_results": [judge.judge(paper) for paper in state["deduped_papers"]]}

    def rank_papers(state: PaperDiscoveryState) -> dict:
        ranked_candidates = [
            {"paper": paper, "judgement": judgement}
            for paper, judgement in zip(state["deduped_papers"], state["judge_results"], strict=False)
        ]
        ranked_candidates.sort(
            key=lambda item: item["judgement"].final_score,
            reverse=True,
        )
        return {
            "judge_results": judge.sort_by_final_score(state["judge_results"]),
            "ranked_candidates": ranked_candidates,
        }

    return {
        "load_memory_context": load_memory_context,
        "rewrite_query": rewrite_query,
        "multi_source_search": multi_source_search,
        "dedup_papers": dedup_papers,
        "judge_papers": judge_papers,
        "rank_papers": rank_papers,
    }


def paper_select_node(state: PaperSelectState) -> PaperSelectState:
    # 1. 去重
    deduplicator = DeDuplicator() # 初始化去重器，加载已知论文（内部已经 loaded known_papers）
    new_papers = deduplicator.dedup(state["papers"])

    # 2. Judge
    judge = LLMJudge()
    judge_results = [judge.judge(paper) for paper in new_papers]
    

    # 3. 排序（可选）
    sorted_results = judge.sort_by_final_score(judge_results)

    # 4. 更新状态
    state["judge_results"] = sorted_results

    return state

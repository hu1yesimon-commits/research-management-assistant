from services.adapters.arxiv_adapter import ArxivAdapter
from services.adapters.openalex_adapter import OpenAlexAdapter
from services.schemas import PaperMetadata

class PaperSearchService:

    def __init__(self, arxiv=None, openalex=None):
        # 这样支持假数据注入
        self.arxiv = arxiv or ArxivAdapter()
        self.openalex = openalex or OpenAlexAdapter()

    def search(self, query: str) -> list[PaperMetadata]:
        # ① arxiv 初步检索
        papers = self.arxiv.search(query) # 这里使用了Arxiv适配器的search方法，返回一个PaperMetadata列表，每个PaperMetadata至少包含arXiv ID、标题、作者等基本信息
        # papers 里面就是 list [Metadata]，每个 Metadata 至少有 arXiv ID 和标题，后续用标题去 openalex 补全其他字段
        if not papers:
            status = getattr(self.arxiv, "last_status", {"status": "unknown"})
            print(f"[paper_search] arXiv returned 0 papers for query {query!r}; status={status}")

        # ② 逐条用 openalex 补全p
        for paper in papers:
            patch = self.openalex.enrich_by_title(paper.title)
            if not patch:
                status = getattr(self.openalex, "last_status", {"status": "unknown"})
                print(
                    f"[paper_search] OpenAlex enrichment skipped for title {paper.title!r}; "
                    f"status={status}"
                )
                continue          # openalex 没找到，跳过，保留原始 paper
            self._merge(paper, patch)

        return papers

    def _merge(self, paper: PaperMetadata, patch: dict) -> None:
        # Only normalized exact title matches are trusted for automatic enrichment.
        if patch.get("match_type") == "exact_normalized":
            if not paper.doi and patch.get("doi"):
                paper.doi = patch["doi"]
                paper.source_ids.doi = patch["doi"]
            if not paper.citation_count and patch.get("citation_count"):
                paper.citation_count = patch["citation_count"]
            if patch.get("openalex_id"):
                paper.source_ids.openalex_id = patch["openalex_id"]
            if not paper.venue and patch.get("venue"):
                paper.venue = patch["venue"]
            if not paper.venue_type and patch.get("venue_type"):
                paper.venue_type = patch["venue_type"]

            paper.raw["openalex"] = patch["_raw"]
        else:
            paper.raw["openalex_candidate"] = patch["_raw"]

        if patch.get("_debug"):
            paper.raw["openalex_debug"] = patch["_debug"]

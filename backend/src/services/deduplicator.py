import json
from pathlib import Path
from services.schemas import PaperMetadata


class DeDuplicator:
    """论文去重器，基于 DOI 和 title 进行去重判断，并持久化已知论文列表。

    可以传入 known_dois 初始化已知 DOI 集合，也可以从存储加载。
    """

    def __init__(self, storage_path: str = "data/known_papers.json", known_dois: set[str] | list[str] | None = None):
        self.storage_path = Path(storage_path)
        if known_dois is None:
            self.known_dois: set[str] = set()
            self._load_known_papers()
        else:
            self.known_dois = {
                normalized
                for normalized in (self._normalize_doi(doi) for doi in known_dois)
                if normalized
            }

    def dedup(self, papers: list[PaperMetadata]) -> list[PaperMetadata]:
        """过滤掉已入库的论文，返回新论文列表"""
        new_papers = []
        seen_dois: set[str] = set()
        seen_titles: set[str] = set()

        for paper in papers:
            doi = self._normalize_doi(paper.doi)
            title = self._normalize_title(paper.title)

            if doi and doi in self.known_dois:
                continue
            if doi and doi in seen_dois:
                continue
            if title and title in seen_titles:
                continue

            new_papers.append(paper)
            if doi:
                seen_dois.add(doi)
            if title:
                seen_titles.add(title)

        return new_papers

    def register(self, paper: PaperMetadata) -> None:
        """论文通过 Judge 后调用，写入去重索引并持久化"""
        doi = self._normalize_doi(paper.doi)

        if not doi:
            return

        self.known_dois.add(doi)
        self._save_known_papers()

    def _load_known_papers(self) -> None:
        """从存储加载已知论文 DOI"""
        if not self.storage_path.exists():
            self.known_dois = set()
            return

        with open(self.storage_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.known_dois = set(data.get("dois", []))

    def _save_known_papers(self) -> None:
        """保存已知论文 DOI"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "dois": sorted(self.known_dois)
        }

        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _normalize_doi(doi: str | None) -> str | None:
        """统一 DOI 格式，避免大小写、空格导致重复判断失败"""
        if not doi:
            return None

        normalized = doi.strip().lower()

        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break

        return normalized or None

    @staticmethod
    def _normalize_title(title: str | None) -> str | None:
        """统一 title 格式，用于当前 batch 的弱去重"""
        if not title:
            return None

        normalized = " ".join(title.strip().lower().split())
        return normalized or None

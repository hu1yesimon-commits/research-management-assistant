import logging
import subprocess
import time
import urllib.parse
import xml.etree.ElementTree as ET

from config import config
from services.schemas import PaperMetadata, PaperId

logger = logging.getLogger(__name__)


class ArxivAdapter:
    source_name = "arxiv"
    API_BASE = "https://export.arxiv.org/api/query"

    def __init__(self, max_results: int | None = None):
        self.max_results = max_results or config.arxiv_max_results
        self.rate_limit = config.arxiv_rate_limit
        self.timeout = config.paper_search_timeout
        self.last_status: dict = {"status": "idle", "source": self.source_name}

    def _set_status(self, status: str, **details) -> None:
        self.last_status = {"status": status, "source": self.source_name, **details}

    def search(self, query: str) -> list[PaperMetadata]:
        params = {
            "search_query": query,
            "max_results": str(self.max_results),
            "sortBy": config.arxiv_sort_by,
            "sortOrder": config.arxiv_sort_order,
        }
        url = f"{self.API_BASE}?{urllib.parse.urlencode(params)}"

        time.sleep(self.rate_limit)

        try:
            result = subprocess.run(
                ["curl", "-sS", "--max-time", str(self.timeout), url],
                capture_output=True,
                text=True,
                timeout=self.timeout + 5,
            )
        except FileNotFoundError:
            self._set_status("curl_missing")
            logger.warning("[arxiv] curl is not installed; cannot query arXiv")
            return []
        except subprocess.TimeoutExpired:
            self._set_status("timeout", timeout_seconds=self.timeout)
            logger.warning("[arxiv] request timed out after %ss", self.timeout)
            return []
        except OSError as exc:
            self._set_status("process_error", error_type=type(exc).__name__)
            logger.warning("[arxiv] failed to execute curl: %s", exc)
            return []

        if result.returncode != 0:
            stderr = result.stderr.strip()
            status = "network_error" if "Could not resolve host" in stderr else "curl_error"
            self._set_status(
                status,
                returncode=result.returncode,
                error=stderr[:300] or "curl returned non-zero exit status",
            )
            logger.warning("[arxiv] curl failed (%s): %s", result.returncode, stderr or "no stderr")
            return []

        if not result.stdout.strip():
            self._set_status("empty_response")
            logger.warning("[arxiv] empty response body")
            return []

        if "Rate exceeded" in result.stdout:
            self._set_status("rate_limited")
            logger.warning("[arxiv] rate limited by upstream")
            return []

        try:
            papers = self._parse_xml(result.stdout)
        except ET.ParseError as exc:
            self._set_status("parse_error", error=str(exc))
            logger.warning("[arxiv] failed to parse XML: %s", exc)
            return []

        self._set_status("ok", result_count=len(papers), query=query)
        return papers

    def _parse_xml(self, xml_text: str) -> list[PaperMetadata]:
        NS = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }

        root = ET.fromstring(xml_text)
        entries = root.findall("atom:entry", NS)

        papers = []
        for entry in entries:
            paper_id = self._get_short_id(entry, NS)
            doi_el = entry.find("arxiv:doi", NS)
            doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None

            paper = PaperMetadata(
                paper_id=f"arxiv_{paper_id}",
                source_ids=PaperId(arxiv_id=paper_id, doi=doi),
                title=self._text(entry, "atom:title", NS) or "",
                authors=self._extract_authors(entry, NS),
                abstract=self._text(entry, "atom:summary", NS),
                published_date=self._extract_date(entry, NS),
                venue=None,
                venue_type=None,
                doi=doi,
                url=self._text(entry, "atom:id", NS),
                pdf_url=self._extract_pdf_url(entry, NS),
                source=self.source_name,
                citation_count=None,
                raw={
                    "entry_id": self._text(entry, "atom:id", NS),
                    "title": self._text(entry, "atom:title", NS),
                    "summary": self._text(entry, "atom:summary", NS),
                    "published": self._text(entry, "atom:published", NS),
                    "updated": self._text(entry, "atom:updated", NS),
                    "doi": doi,
                    "journal_ref": self._text(entry, "arxiv:journal_ref", NS),
                    "primary_category": self._attr(entry, "arxiv:primary_category", "term", NS),
                    "categories": [
                        cat.get("term")
                        for cat in entry.findall("atom:category", NS)
                        if cat.get("term")
                    ],
                    "pdf_url": self._extract_pdf_url(entry, NS),
                    "comment": self._text(entry, "arxiv:comment", NS),
                },
            )
            papers.append(paper)

        return papers

    # ── XML helpers ──────────────────────────────────────────

    def _text(self, el, tag, ns) -> str | None:
        child = el.find(tag, ns)
        return child.text.strip() if child is not None and child.text else None

    def _attr(self, el, tag, attr, ns) -> str | None:
        child = el.find(tag, ns)
        return child.get(attr) if child is not None else None

    def _get_short_id(self, entry, ns) -> str:
        """Extract arxiv ID from <id>http://arxiv.org/abs/2401.12345v1</id>."""
        id_url = self._text(entry, "atom:id", ns) or ""
        # http://arxiv.org/abs/2401.12345v1 → 2401.12345
        return id_url.split("/abs/")[-1].split("v")[0]

    def _extract_authors(self, entry, ns) -> list[str]:
        return [
            a.find("atom:name", ns).text.strip()
            for a in entry.findall("atom:author", ns)
            if a.find("atom:name", ns) is not None
        ]

    def _extract_date(self, entry, ns) -> str | None:
        published = self._text(entry, "atom:published", ns)
        if published:
            return published[:10]  # "2024-01-15T00:00:00Z" → "2024-01-15"
        return None

    def _extract_pdf_url(self, entry, ns) -> str | None:
        for link in entry.findall("atom:link", ns):
            if link.get("title") == "pdf":
                return link.get("href")
        return None

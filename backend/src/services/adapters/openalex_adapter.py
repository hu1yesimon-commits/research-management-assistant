import logging
import re
import time

import requests

from config import config

logger = logging.getLogger(__name__)

class OpenAlexAdapter:
    BASE_URL = "https://api.openalex.org"

    def __init__(self):
        self.email = config.openalex_mailto       # 礼貌参数
        self.api_key = config.openalex_api_key    # 可选，有 key 限速更高
        self.rate_limit = config.openalex_rate_limit
        self.timeout = config.paper_search_timeout
        self.last_status: dict = {"status": "idle", "source": "openalex"}

    def _set_status(self, status: str, **details) -> None:
        self.last_status = {"status": status, "source": "openalex", **details}

    def _build_params(self) -> dict:
        params = {}
        if self.email:
            params["mailto"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def _extract_doi(self, doi_url: str | None) -> str | None:
        if not doi_url:
            return None
        return doi_url.replace("https://doi.org/", "")

    def _as_dict(self, value) -> dict:
        return value if isinstance(value, dict) else {}

    def _extract_venue(self, result: dict) -> str | None:
        loc = self._as_dict(result.get("primary_location"))
        source = self._as_dict(loc.get("source"))
        return source.get("display_name")

    def _extract_venue_type(self, result: dict) -> str | None:
        loc = self._as_dict(result.get("primary_location"))
        source = self._as_dict(loc.get("source"))
        type_str = source.get("type")
        if not type_str:
            return None
        type_map = {
            "journal": "journal",
            "conference": "conference",
            "repository": "preprint",
        }
        return type_map.get(type_str, "unknown")

    def _extract_publisher(self, result: dict) -> str | None:
        loc = self._as_dict(result.get("primary_location"))
        source = self._as_dict(loc.get("source"))
        return source.get("host_organization_name")

    def _extract_open_access(self, result: dict) -> bool | None:
        open_access = self._as_dict(result.get("open_access"))
        return open_access.get("is_oa")

    def _extract_openalex_id(self, result: dict) -> str | None:
        raw_id = result.get("id")
        if not raw_id or not isinstance(raw_id, str):
            return None
        return raw_id.replace("https://openalex.org/", "")

    def _normalize_title(self, title: str | None) -> str:
        if not title:
            return ""
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", title.lower())).strip()

    def search_by_title(self, title: str) -> dict | None:
        url = f"{self.BASE_URL}/works"
        params = self._build_params()
        params["search"] = title
        params["per_page"] = 1          # 只要最相关的一条

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
        except requests.Timeout:
            self._set_status("timeout", timeout_seconds=self.timeout, query_title=title)
            logger.warning("[openalex] request timed out after %ss", self.timeout)
            return None
        except requests.RequestException as exc:
            self._set_status("network_error", error_type=type(exc).__name__, error=str(exc), query_title=title)
            logger.warning("[openalex] request failed for title '%s': %s", title, exc)
            return None
        finally:
            time.sleep(self.rate_limit)     # 遵守限速

        if response.status_code == 429:
            self._set_status("rate_limited", query_title=title)
            logger.warning("[openalex] rate limited for title '%s'", title)
            return None

        if response.status_code != 200:
            self._set_status("http_error", status_code=response.status_code, query_title=title)
            logger.warning("[openalex] non-200 response for title '%s': %s", title, response.status_code)
            return None

        try:
            data = response.json()
        except ValueError as exc:
            self._set_status("parse_error", error=str(exc), query_title=title)
            logger.warning("[openalex] failed to parse JSON for title '%s': %s", title, exc)
            return None

        if data["meta"]["count"] == 0:
            self._set_status("no_match", query_title=title)
            return None

        result = data["results"][0]
        matched_title = result.get("display_name") or result.get("title") or ""
        normalized_input = self._normalize_title(title)
        normalized_match = self._normalize_title(matched_title)
        match_type = "exact_normalized" if normalized_input == normalized_match else "search_top_result"
        self._set_status(
            "ok",
            query_title=title,
            matched_title=matched_title,
            match_type=match_type,
        )
        return result       # 返回第一条，最相关

    def _inverted_abstract_to_text(self, inverted_index: dict | None) -> str | None:
        if not inverted_index:
            return None
        # 按位置排序所有词，再拼接
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort(key=lambda x: x[0])
        return " ".join(word for _, word in word_positions)

    def enrich_by_title(self, paper_title: str) -> dict | None:
        """
        用 title 搜索 OpenAlex，返回可以补全的字段。
        不返回 PaperMetadata 本身，只返回一个"补丁" dict，调用方负责合并。
        """
        result = self.search_by_title(paper_title)
        if not result:
            return None

        matched_title = result.get("display_name") or result.get("title") or ""
        normalized_input = self._normalize_title(paper_title)
        normalized_match = self._normalize_title(matched_title)
        match_type = "exact_normalized" if normalized_input == normalized_match else "search_top_result"
        match_confidence = 1.0 if match_type == "exact_normalized" else 0.5

        return {
            "doi": self._extract_doi(result.get("doi")),
            "venue": self._extract_venue(result),
            "venue_type": self._extract_venue_type(result),
            "citation_count": result.get("cited_by_count"),
            "is_open_access": self._extract_open_access(result),
            "publisher": self._extract_publisher(result),
            "openalex_id": self._extract_openalex_id(result),
            "match_type": match_type,
            "match_confidence": match_confidence,
            "matched_title": matched_title,
            "_debug": {
                "query_title": paper_title,
                "matched_title": matched_title,
                "match_type": match_type,
                "match_confidence": match_confidence,
            },
            "_raw": result,
        }

import argparse

from services.adapters.arxiv_adapter import ArxivAdapter
from services.adapters.openalex_adapter import OpenAlexAdapter
from services.paper_search import PaperSearchService


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual smoke check for arXiv/OpenAlex adapters.")
    parser.add_argument("query", nargs="?", default="graph reconstruction")
    parser.add_argument("--max-results", type=int, default=3)
    args = parser.parse_args()

    arxiv = ArxivAdapter(max_results=args.max_results)
    openalex = OpenAlexAdapter()
    service = PaperSearchService(arxiv=arxiv, openalex=openalex)

    papers = service.search(args.query)

    print(f"QUERY: {args.query}")
    print(f"ARXIV_STATUS: {arxiv.last_status}")
    print(f"ARXIV_COUNT: {len(papers)}")

    enriched_count = 0
    for idx, paper in enumerate(papers[: args.max_results], start=1):
        if paper.raw.get("openalex"):
            enriched_count += 1
        print(f"PAPER_{idx}_TITLE: {paper.title}")
        print(f"PAPER_{idx}_DOI: {paper.doi}")
        print(f"PAPER_{idx}_OPENALEX_ID: {paper.source_ids.openalex_id}")
        print(f"PAPER_{idx}_OPENALEX_DEBUG: {paper.raw.get('openalex_debug')}")

    print(f"OPENALEX_STATUS: {openalex.last_status}")
    print(f"OPENALEX_ENRICHED_COUNT: {enriched_count}")


if __name__ == "__main__":
    main()

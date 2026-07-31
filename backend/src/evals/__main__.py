from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.evaluator import evaluate_dataset
from evals.schema import GoldDataset, ObservationDataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate structured research-agent observations against Gold."
    )
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--observed", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    gold = GoldDataset.from_path(args.gold)
    observations = ObservationDataset.from_path(args.observed)
    report = evaluate_dataset(gold, observations)
    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.hard_gates_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

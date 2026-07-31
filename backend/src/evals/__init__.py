"""Deterministic evaluation contracts for the research assistant."""

from evals.evaluator import evaluate_dataset
from evals.schema import GoldDataset, ObservationDataset

__all__ = ["GoldDataset", "ObservationDataset", "evaluate_dataset"]

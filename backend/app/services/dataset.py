"""Derive a per-objective dataset schema + scaler + validation set from a labeled CSV.

A coordinator uploads a small labeled validation CSV when creating a training objective.
The server derives the ordered feature columns, the standardization scaler (per-feature
mean/std), and the standardized validation rows (the "digital twin"). Clients later fetch
the schema + scaler so every participant preprocesses features identically.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DerivedSchema:
    feature_columns: list[str]
    target_column: str
    positive_label: str
    negative_label: str
    n_features: int
    scaler_mean: list[float]
    scaler_scale: list[float]
    twin_x: list[list[float]]  # standardized validation features
    twin_y: list[int]  # binary labels (1 == positive_label)


def parse_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("The CSV has no header row")
    rows = [row for row in reader]
    if not rows:
        raise ValueError("The CSV has no data rows")
    return list(reader.fieldnames), rows


def detect_labels(
    text: str, target_column: str | None = None
) -> dict[str, object]:
    """Parse a CSV and return the two class labels + a suggested positive label.

    This powers the preview endpoint so the coordinator can see what the server
    detected before committing to a choice.
    """
    columns, rows = parse_csv(text)
    target = target_column or columns[-1]
    if target not in columns:
        raise ValueError(f"Target column '{target}' is not present in the CSV")
    raw_targets = [row[target] for row in rows]
    labels = sorted({value for value in raw_targets})
    if len(labels) != 2:
        raise ValueError(
            f"Target column '{target}' must have exactly two classes; found {len(labels)}"
        )
    return {
        "labels": labels,
        "suggested_positive": _pick_positive(labels),
        "target_column": target,
    }


def derive_schema(
    text: str,
    target_column: str | None = None,
    positive_label: str | None = None,
) -> DerivedSchema:
    """Build the schema from CSV text.

    *target_column* defaults to the last column.  *positive_label*, when
    provided, must be one of the two detected classes and is used directly;
    otherwise the heuristic ``_pick_positive`` supplies a best-effort guess.
    """
    columns, rows = parse_csv(text)
    target = target_column or columns[-1]
    if target not in columns:
        raise ValueError(f"Target column '{target}' is not present in the CSV")
    feature_columns = [column for column in columns if column != target]
    if not feature_columns:
        raise ValueError("The CSV needs at least one feature column besides the target")

    raw_targets = [row[target] for row in rows]
    labels = sorted({value for value in raw_targets})
    if len(labels) != 2:
        raise ValueError(
            f"Target column '{target}' must have exactly two classes; found {len(labels)}"
        )

    # Use the coordinator's explicit choice when given; fall back to heuristic.
    if positive_label is not None:
        if positive_label not in labels:
            raise ValueError(
                f"positive_label '{positive_label}' is not one of the detected "
                f"classes: {labels}"
            )
        positive = positive_label
    else:
        positive = _pick_positive(labels)
    negative = labels[0] if labels[1] == positive else labels[1]

    try:
        features = np.asarray(
            [[float(row[column]) for column in feature_columns] for row in rows],
            dtype=np.float64,
        )
    except ValueError as exc:
        raise ValueError("All feature columns must contain numeric values") from exc
    if not np.all(np.isfinite(features)):
        raise ValueError("Feature values must be finite numbers")

    y = np.asarray([1 if value == positive else 0 for value in raw_targets], dtype=np.int64)

    mean = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale == 0] = 1.0
    standardized = (features - mean) / scale

    return DerivedSchema(
        feature_columns=feature_columns,
        target_column=target,
        positive_label=str(positive),
        negative_label=str(negative),
        n_features=len(feature_columns),
        scaler_mean=mean.tolist(),
        scaler_scale=scale.tolist(),
        twin_x=np.round(standardized, 6).tolist(),
        twin_y=y.tolist(),
    )


_TRUTHY = {"1", "true", "yes", "positive", "pos", "malignant", "abnormal", "disease", "y"}


def _pick_positive(labels: list[str]) -> str:
    for label in labels:
        if label.strip().lower() in _TRUTHY:
            return label
    # Fall back to the numerically larger / lexicographically later label.
    try:
        return max(labels, key=lambda value: float(value))
    except ValueError:
        return sorted(labels)[-1]

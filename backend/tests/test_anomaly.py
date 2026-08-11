from __future__ import annotations

from backend.app.config import Settings
from backend.app.services.anomaly import AnomalyDetector

TEST_SECRET = "test-secret-key-that-is-longer-than-thirty-two-characters"


def detector(**overrides) -> AnomalyDetector:
    return AnomalyDetector(Settings(secret_key=TEST_SECRET, **overrides))


def test_fewer_than_three_entries_are_not_screened() -> None:
    assert detector().flag_outliers([("h1", [1.0, 0.0]), ("h2", [-1.0, 0.0])]) == {}


def test_opposing_update_is_flagged() -> None:
    """An update that opposes the consensus (negative cosine) **and** has a high
    Euclidean distance should still be flagged under the dual-signal rule."""
    flagged = detector().flag_outliers(
        [
            ("h1", [1.0, 0.1, 0.0]),
            ("h2", [1.1, 0.05, 0.02]),
            ("h3", [0.95, 0.08, -0.01]),
            ("h4", [-1.0, -0.1, 0.0]),
        ]
    )
    assert set(flagged) == {"h4"}
    assert any("consensus" in reason for reason in flagged["h4"])


def test_aligned_updates_pass() -> None:
    flagged = detector().flag_outliers(
        [
            ("h1", [1.0, 0.1]),
            ("h2", [1.05, 0.12]),
            ("h3", [0.98, 0.09]),
        ]
    )
    assert flagged == {}


def test_scaled_but_aligned_update_passes() -> None:
    """A scaled-up but same-direction update (high Euclidean distance, good
    cosine similarity) should NOT be flagged — the dual-signal rule filters
    out harmless scale differences."""
    flagged = detector().flag_outliers(
        [
            ("h1", [1.0, 0.1, 0.0]),
            ("h2", [1.1, 0.12, 0.01]),
            ("h3", [0.95, 0.08, -0.01]),
            # h4 points in the same direction but is ~10x the magnitude.
            ("h4", [10.0, 1.0, 0.0]),
        ]
    )
    # h4 has a very high Euclidean distance but excellent cosine similarity
    # → only one signal fires → not flagged.
    assert "h4" not in flagged


def test_both_signals_abnormal_is_flagged() -> None:
    """When both Euclidean distance AND cosine similarity are abnormal, the
    update should be flagged."""
    flagged = detector().flag_outliers(
        [
            ("h1", [1.0, 0.1, 0.0]),
            ("h2", [1.1, 0.05, 0.02]),
            ("h3", [0.95, 0.08, -0.01]),
            # h4 is far away AND points in a different direction.
            ("h4", [-5.0, 3.0, -2.0]),
        ]
    )
    assert "h4" in flagged
    assert any("scale and direction" in r for r in flagged["h4"])

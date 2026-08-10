from __future__ import annotations

import numpy as np

from ..config import Settings


class AnomalyDetector:
    """Cross-client poisoning screen run over a round's verified updates.

    Uses a **dual-signal** approach: an update is flagged only when it looks
    abnormal on *both* Euclidean distance (MAD z-score) **and** cosine
    similarity vs the round median.  This filters out harmless scale
    differences (high Euclidean but good cosine) from genuinely poisoned
    updates (high Euclidean *and* low cosine).
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def flag_outliers(self, entries: list[tuple[str, list[float]]]) -> dict[str, list[str]]:
        """Return {entry_id: reasons} for updates that deviate from the round consensus."""
        if len(entries) < 3:
            return {}

        matrix = np.asarray([weights for _, weights in entries], dtype=np.float64)
        reference = np.median(matrix, axis=0)
        reference_norm = float(np.linalg.norm(reference))
        flagged: dict[str, list[str]] = {}

        # --- Euclidean MAD z-scores ---
        distances = np.linalg.norm(matrix - reference, axis=1)
        median_distance = float(np.median(distances))
        mad = float(np.median(np.abs(distances - median_distance)))

        for index, (entry_id, _) in enumerate(entries):
            euclidean_abnormal = False
            cosine_abnormal = False
            euclidean_detail = ""
            cosine_detail = ""

            # Euclidean MAD check
            if mad > 1e-12:
                z_score = 0.6745 * (distances[index] - median_distance) / mad
                if z_score > self.settings.anomaly_mad_threshold:
                    euclidean_abnormal = True
                    euclidean_detail = f"modified z-score {z_score:.2f}"

            # Cosine similarity check
            row = matrix[index]
            row_norm = float(np.linalg.norm(row))
            if row_norm > 1e-12 and reference_norm > 1e-12:
                cosine = float(row @ reference) / (row_norm * reference_norm)
                if cosine < self.settings.anomaly_cosine_threshold:
                    cosine_abnormal = True
                    cosine_detail = f"cosine similarity {cosine:.2f}"

            # Flag only when BOTH signals are abnormal.
            if euclidean_abnormal and cosine_abnormal:
                reason = (
                    f"Update deviates from the round consensus on both scale and "
                    f"direction ({euclidean_detail}; {cosine_detail})"
                )
                flagged[entry_id] = [reason]

        return flagged

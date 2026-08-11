from __future__ import annotations

from ..models import Hospital, TrainingObjective


class RoutingService:
    def select_hospitals(self, objective: TrainingObjective, hospitals: list[Hospital]) -> list[Hospital]:
        active = [
            hospital
            for hospital in hospitals
            if hospital.active and hospital.blockchain_registered and hospital.wallet_address
        ]
        # Hard-filter by specialty when enough specialists are available.
        specialists = [
            hospital for hospital in active
            if hospital.specialty.lower() == objective.specialty.lower()
        ]
        pool = specialists if len(specialists) >= objective.min_participants else active
        scored = sorted(
            pool,
            key=lambda hospital: self._score(objective, hospital),
            reverse=True,
        )
        return scored[: max(objective.min_participants, 1)]

    def _score(self, objective: TrainingObjective, hospital: Hospital) -> float:
        # Specialty bonus retained so specialists still rank higher when the
        # pool was widened due to insufficient specialist count.
        specialty_match = 30 if hospital.specialty.lower() == objective.specialty.lower() else 0
        region_bonus = 4 if hospital.region in objective.routing_metadata.get("preferred_regions", []) else 0
        sample_score = min(hospital.samples / 1000, 25)
        reputation_score = hospital.reputation / 4
        return specialty_match + region_bonus + sample_score + reputation_score

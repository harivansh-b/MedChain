from __future__ import annotations

from backend.app.models import Hospital, TrainingObjective
from backend.app.services.routing import RoutingService


def _hospital(
    id: str, specialty: str, samples: int = 1000, reputation: int = 80
) -> Hospital:
    return Hospital(
        id=id,
        org_id=f"org_{id}",
        name=f"Hospital {id}",
        region="North",
        samples=samples,
        specialty=specialty,
        reputation=reputation,
        active=True,
        blockchain_registered=True,
        wallet_address=f"0x{'0' * 39}{id[-1]}",
    )


def _objective(specialty: str = "Radiology", min_participants: int = 2) -> TrainingObjective:
    return TrainingObjective(
        name="Test objective",
        disease_category=specialty.lower(),
        specialty=specialty,
        min_participants=min_participants,
    )


def test_specialists_are_preferred() -> None:
    """When enough specialists exist, non-specialists should be excluded."""
    hospitals = [
        _hospital("h1", "Radiology", samples=500),
        _hospital("h2", "Radiology", samples=800),
        _hospital("h3", "Radiology", samples=600),
        _hospital("h4", "Cardiology", samples=5000),  # big generalist — excluded
        _hospital("h5", "Neurology", samples=3000),   # big generalist — excluded
    ]
    selected = RoutingService().select_hospitals(_objective(min_participants=2), hospitals)
    assert len(selected) == 2
    assert all(h.specialty == "Radiology" for h in selected)


def test_fallback_when_too_few_specialists() -> None:
    """When fewer specialists exist than min_participants, the pool widens
    but specialists should still rank higher."""
    hospitals = [
        _hospital("h1", "Radiology", samples=500, reputation=80),
        _hospital("h2", "Cardiology", samples=5000, reputation=90),
        _hospital("h3", "Neurology", samples=3000, reputation=85),
        _hospital("h4", "Cardiology", samples=2000, reputation=70),
    ]
    selected = RoutingService().select_hospitals(_objective(min_participants=3), hospitals)
    assert len(selected) == 3
    # The one specialist (h1) should be included despite lower sample count.
    assert any(h.id == "h1" for h in selected)


def test_specialty_match_is_case_insensitive() -> None:
    hospitals = [
        _hospital("h1", "radiology"),
        _hospital("h2", "RADIOLOGY"),
        _hospital("h3", "Cardiology"),
    ]
    selected = RoutingService().select_hospitals(_objective("Radiology", min_participants=2), hospitals)
    assert len(selected) == 2
    assert all(h.specialty.lower() == "radiology" for h in selected)

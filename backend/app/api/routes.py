from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..models import (
    AuditEvent,
    DashboardSummary,
    DigitalTwinRecord,
    Hospital,
    ModelVersion,
    Organization,
    Submission,
    TrainingObjective,
    TrainingRound,
    User,
    ValidationReport,
    new_id,
)
from ..services.dataset import derive_schema, detect_labels
from ..services.runtime import MedChainRuntime
from ..store import Repository
from .auth_routes import auth_router
from .dependencies import get_current_user, get_repo, require_roles

router = APIRouter()
router.include_router(auth_router)


class HospitalCreate(BaseModel):
    id: str | None = None
    name: str
    region: str
    samples: int = Field(gt=0)
    specialty: str
    reputation: int = Field(default=80, ge=0, le=100)
    org_id: str | None = None
    wallet_address: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class HospitalPatch(BaseModel):
    name: str | None = None
    region: str | None = None
    samples: int | None = Field(default=None, gt=0)
    specialty: str | None = None
    reputation: int | None = Field(default=None, ge=0, le=100)
    active: bool | None = None
    wallet_address: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{40}$")
    metadata: dict[str, Any] | None = None


class ObjectiveCreate(BaseModel):
    name: str
    disease_category: str
    specialty: str
    target_metric: str = "accuracy"
    target_value: float = 0.9
    min_participants: int = 3
    routing_metadata: dict[str, Any] = Field(default_factory=dict)
    # Optional labeled validation CSV (raw text). When present, the server derives the
    # per-objective feature schema + scaler + validation set from it.
    validation_csv: str | None = None
    target_column: str | None = None
    # Explicit positive-class label. When None the server uses a word-match heuristic.
    positive_label: str | None = None


class DetectLabelsRequest(BaseModel):
    validation_csv: str
    target_column: str | None = None


class RoundCreate(BaseModel):
    objective_id: str | None = None


class SubmissionCreate(BaseModel):
    hospital_id: str
    update: dict[str, Any]


class InferenceRequest(BaseModel):
    features: list[float] = Field(min_length=1, max_length=1000)
    objective_id: str | None = None


def get_runtime(request: Request) -> MedChainRuntime:
    return request.app.state.runtime


def dump(model: Any) -> Any:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    if hasattr(model, "json"):
        return json.loads(model.json())
    return model


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    repo: Repository = request.app.state.repo
    return {
        "ok": True,
        "app": request.app.state.settings.app_name,
        "mongodb_connected": repo.mongo_enabled(),
        "artifact_storage": "azure_blob",
        "azure_blob_connected": request.app.state.runtime.artifacts.connected,
        "blockchain_connected": request.app.state.runtime.blockchain.connected,
        "blockchain_chain_id": request.app.state.runtime.blockchain.chain_id,
        "blockchain_signer": request.app.state.runtime.blockchain.signer_address,
        "blockchain_height": request.app.state.runtime.blockchain.height,
    }


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    payload = dump(user)
    payload.pop("password_hash", None)
    return payload


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(get_current_user),
) -> DashboardSummary:
    _ = user
    return await runtime.dashboard_summary()


@router.get("/hospitals", response_model=list[Hospital])
async def list_hospitals(
    repo: Repository = Depends(get_repo),
    user: User = Depends(get_current_user),
) -> list[Hospital]:
    _ = user
    return sorted(await repo.list("hospitals", Hospital), key=lambda hospital: hospital.id)


@router.post("/hospitals", response_model=Hospital)
async def create_hospital(
    body: HospitalCreate,
    request: Request,
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin")),
) -> Hospital:
    hospital_id = body.id or new_id("hsp")
    if await repo.get("hospitals", hospital_id, Hospital):
        raise HTTPException(status_code=409, detail="Hospital id already exists")

    if body.org_id:
        organization = await repo.get("organizations", body.org_id, Organization)
        if organization is None or organization.type != "hospital":
            raise HTTPException(status_code=400, detail="org_id must identify an existing hospital organization")
    else:
        organization = await repo.put(
            "organizations",
            Organization(name=body.name, type="hospital", tier="consortium_node"),
        )

    hospital = Hospital(
        id=hospital_id,
        org_id=organization.id,
        name=body.name,
        region=body.region,
        samples=body.samples,
        specialty=body.specialty,
        reputation=body.reputation,
        wallet_address=body.wallet_address,
        metadata=body.metadata,
    )
    saved = await repo.put("hospitals", hospital)
    await request.app.state.runtime.audit.record("hospital.created", "hospital", saved.id, user)
    return saved


@router.patch("/hospitals/{hospital_id}", response_model=Hospital)
async def patch_hospital(
    hospital_id: str,
    body: HospitalPatch,
    request: Request,
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin", "hospital_admin")),
) -> Hospital:
    hospital = await repo.get("hospitals", hospital_id, Hospital)
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    if user.role == "hospital_admin" and user.org_id != hospital.org_id:
        raise HTTPException(status_code=403, detail="Hospital administrators may only edit their own organization")
    patch = body.model_dump(exclude_unset=True)
    if "wallet_address" in patch and patch["wallet_address"] != hospital.wallet_address:
        hospital.blockchain_registered = False
        hospital.registry_tx_hash = None
        hospital.reputation_tx_hash = None
    for key, value in patch.items():
        setattr(hospital, key, value)
    saved = await repo.put("hospitals", hospital)
    await request.app.state.runtime.audit.record("hospital.updated", "hospital", saved.id, user)
    return saved


@router.post("/hospitals/{hospital_id}/blockchain/register", response_model=Hospital)
async def register_hospital_on_chain(
    hospital_id: str,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin")),
) -> Hospital:
    try:
        return await runtime.register_hospital_on_chain(hospital_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/hospitals/{hospital_id}/reputation/history")
async def hospital_reputation_history(
    hospital_id: str,
    repo: Repository = Depends(get_repo),
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(
        require_roles("platform_admin", "auditor", "research_partner", "hospital_admin")
    ),
) -> dict[str, Any]:
    hospital = await repo.get("hospitals", hospital_id, Hospital)
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    if user.role == "hospital_admin" and user.org_id != hospital.org_id:
        raise HTTPException(status_code=403, detail="Hospital administrators may only view their own organization")
    if not hospital.wallet_address:
        raise HTTPException(status_code=400, detail="Hospital has no wallet address")
    return {
        "hospital_id": hospital.id,
        "wallet_address": hospital.wallet_address,
        "reputation": hospital.reputation,
        "history": runtime.blockchain.reputation_history(hospital.wallet_address),
    }


@router.get("/training-objectives", response_model=list[TrainingObjective])
async def list_objectives(
    repo: Repository = Depends(get_repo),
    user: User = Depends(get_current_user),
) -> list[TrainingObjective]:
    _ = user
    return await repo.list("training_objectives", TrainingObjective)


@router.post("/training-objectives/detect-labels")
async def detect_labels_endpoint(
    body: DetectLabelsRequest,
    user: User = Depends(require_roles("platform_admin", "hospital_admin")),
) -> dict[str, Any]:
    """Parse a validation CSV and return the two detected class labels + a
    suggested positive label.  The coordinator reviews this before creating the
    objective with an explicit ``positive_label``."""
    _ = user
    try:
        return detect_labels(body.validation_csv, body.target_column)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/training-objectives", response_model=TrainingObjective)
async def create_objective(
    body: ObjectiveCreate,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin", "hospital_admin")),
) -> TrainingObjective:
    fields = body.model_dump()
    validation_csv = fields.pop("validation_csv", None)
    target_column = fields.pop("target_column", None)
    positive_label = fields.pop("positive_label", None)
    objective = TrainingObjective(**fields)
    twin_record: DigitalTwinRecord | None = None
    if validation_csv:
        try:
            schema = derive_schema(validation_csv, target_column, positive_label=positive_label)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        objective.has_schema = True
        objective.feature_columns = schema.feature_columns
        objective.target_column = schema.target_column
        objective.positive_label = schema.positive_label
        objective.negative_label = schema.negative_label
        objective.n_features = schema.n_features
        objective.scaler_mean = schema.scaler_mean
        objective.scaler_scale = schema.scaler_scale
        twin_record = DigitalTwinRecord(
            objective_id=objective.id,
            n_features=schema.n_features,
            X=schema.twin_x,
            y=schema.twin_y,
            positive_label=schema.positive_label,
            negative_label=schema.negative_label,
        )
    return await runtime.create_objective(objective, user, twin_record=twin_record)


@router.get("/training-objectives/{objective_id}/schema")
async def objective_schema(
    objective_id: str,
    repo: Repository = Depends(get_repo),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user
    objective = await repo.get("training_objectives", objective_id, TrainingObjective)
    if objective is None:
        raise HTTPException(status_code=404, detail="Training objective not found")
    if not objective.has_schema:
        raise HTTPException(status_code=404, detail="This objective has no dataset schema")
    return {
        "objective_id": objective.id,
        "feature_columns": objective.feature_columns,
        "target_column": objective.target_column,
        "n_features": objective.n_features,
        "expected_dimension": (objective.n_features or 0) + 1,
        "scaler": {"mean": objective.scaler_mean, "scale": objective.scaler_scale},
        "positive_label": objective.positive_label,
        "negative_label": objective.negative_label,
    }


@router.get("/rounds", response_model=list[TrainingRound])
async def list_rounds(
    repo: Repository = Depends(get_repo),
    user: User = Depends(get_current_user),
) -> list[TrainingRound]:
    _ = user
    return sorted(await repo.list("rounds", TrainingRound), key=lambda item: item.round_number)


@router.get("/rounds/{round_id}", response_model=TrainingRound)
async def get_round(
    round_id: str,
    repo: Repository = Depends(get_repo),
    user: User = Depends(get_current_user),
) -> TrainingRound:
    _ = user
    training_round = await repo.get("rounds", round_id, TrainingRound)
    if not training_round:
        raise HTTPException(status_code=404, detail="Round not found")
    return training_round


@router.post("/rounds", response_model=TrainingRound)
async def create_round(
    body: RoundCreate,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin", "hospital_admin")),
) -> TrainingRound:
    try:
        return await runtime.create_round(body.objective_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/rounds/{round_id}/cancel", response_model=TrainingRound)
async def cancel_round(
    round_id: str,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin")),
) -> TrainingRound:
    try:
        return await runtime.cancel_round(round_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/rounds/{round_id}/validations", response_model=list[ValidationReport])
async def round_validations(
    round_id: str,
    repo: Repository = Depends(get_repo),
    user: User = Depends(
        require_roles("platform_admin", "auditor", "hospital_admin", "research_partner")
    ),
) -> list[ValidationReport]:
    _ = user
    reports = await repo.list("validation_reports", ValidationReport, round_id=round_id)
    return sorted(reports, key=lambda report: report.created_at)


@router.post("/rounds/{round_id}/blockchain/retry", response_model=TrainingRound)
async def retry_round_blockchain(
    round_id: str,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin")),
) -> TrainingRound:
    try:
        return await runtime.retry_round_blockchain(round_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/rounds/{round_id}/submissions",
    response_model=Submission,
    response_model_exclude={"weights"},
)
async def submit_update(
    round_id: str,
    body: SubmissionCreate,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("hospital_admin", "hospital_node")),
) -> Submission:
    try:
        return await runtime.submit_external_update(round_id, body.hospital_id, body.update, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/inference/predict")
async def inference_predict(
    body: InferenceRequest,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("clinic_user", "platform_admin")),
) -> dict[str, Any]:
    try:
        return await runtime.run_inference(body.features, user, objective_id=body.objective_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/model-versions", response_model=list[ModelVersion])
async def list_model_versions(
    repo: Repository = Depends(get_repo),
    user: User = Depends(get_current_user),
) -> list[ModelVersion]:
    _ = user
    return sorted(await repo.list("model_versions", ModelVersion), key=lambda item: item.round)


@router.get("/model-versions/current", response_model=ModelVersion)
async def current_model(
    objective_id: str | None = None,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(get_current_user),
) -> ModelVersion:
    _ = user
    try:
        return await runtime.current_model(objective_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/blockchain/contributions")
async def blockchain_contributions(
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin", "auditor", "research_partner")),
) -> list[dict[str, Any]]:
    _ = user
    submissions = await repo.list("submissions", Submission)
    results: list[dict[str, Any]] = []
    for submission in submissions:
        if not submission.blockchain_tx_hash:
            continue
        payload = dump(submission)
        payload.pop("weights", None)
        results.append(payload)
    return sorted(results, key=lambda item: item["submitted_at"])


@router.get("/blockchain/blocks")
async def blockchain_blocks(
    limit: int = 100,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin", "auditor", "research_partner")),
) -> list[dict[str, Any]]:
    _ = user
    return runtime.blockchain.export_blocks(limit=max(1, min(limit, 1000)))


@router.get("/blockchain/verify")
async def blockchain_verify(
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin", "auditor", "research_partner")),
) -> dict[str, Any]:
    _ = user
    return runtime.blockchain.verify()


@router.get("/audit/events", response_model=list[AuditEvent])
async def audit_events(
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin", "auditor")),
) -> list[AuditEvent]:
    _ = user
    return sorted(await repo.list("audit_events", AuditEvent), key=lambda item: item.created_at)


@router.get("/compliance/exports")
async def compliance_export(
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin", "auditor")),
) -> dict[str, Any]:
    return await runtime.compliance_export(user)

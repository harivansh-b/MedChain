from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = "MedChain AI Backend"
    api_prefix: str = ""
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    secret_key: str = ""
    access_token_minutes: int = 120
    refresh_token_days: int = 14
    invitation_expires_days: int = 7
    reset_token_minutes: int = 60
    brevo_api_key: str | None = None
    mail_from_email: str | None = None
    mail_from_name: str = "MedChain"
    frontend_base_url: str = "http://localhost:5173"
    mongodb_uri: str | None = None
    mongodb_name: str = "medchain"
    azure_storage_connection_string: str | None = None
    azure_storage_account_url: str | None = None
    azure_storage_container: str | None = None
    chain_id: int = 7777
    signer_private_key: str | None = None
    # "evm" runs the real Solidity contracts on an in-process EVM (free, auto, no node);
    # "embedded" uses the hand-rolled MongoDB ledger. EVM falls back to embedded on failure.
    chain_backend: str = "evm"
    digital_twin_path: str | None = str(Path(__file__).resolve().parent / "data" / "digital_twin.json")
    twin_floor_accuracy: float = 0.60
    twin_regression_tolerance: float = 0.05
    anomaly_distance_cap: float = 10.0
    anomaly_mad_threshold: float = 3.5
    anomaly_cosine_threshold: float = 0.5
    reported_metric_tolerance: float = 0.30
    reputation_reward: int = 2
    reputation_penalty: int = 10
    inference_low_confidence: float = 0.70
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_name: str = "Platform Administrator"

    def validate(
        self,
        require_mongodb: bool = True,
        require_azure_storage: bool = True,
    ) -> None:
        if len(self.secret_key) < 32:
            raise RuntimeError("MEDCHAIN_SECRET_KEY must contain at least 32 characters")
        if require_mongodb and not self.mongodb_uri:
            raise RuntimeError("MEDCHAIN_MONGODB_URI is required")
        if require_azure_storage:
            if not self.azure_storage_container:
                raise RuntimeError("AZURE_STORAGE_CONTAINER is required")
            if not self.azure_storage_connection_string and not self.azure_storage_account_url:
                raise RuntimeError(
                    "AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL is required"
                )
        if self.signer_private_key and not re.fullmatch(
            r"(?:0x)?[0-9a-fA-F]{64}", self.signer_private_key
        ):
            raise RuntimeError("MEDCHAIN_SIGNER_PRIVATE_KEY must be a 32-byte hex private key")
        if bool(self.bootstrap_admin_email) != bool(self.bootstrap_admin_password):
            raise RuntimeError(
                "MEDCHAIN_BOOTSTRAP_ADMIN_EMAIL and MEDCHAIN_BOOTSTRAP_ADMIN_PASSWORD must be set together"
            )
        if self.bootstrap_admin_password and len(self.bootstrap_admin_password) < 12:
            raise RuntimeError("MEDCHAIN_BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters")
        if self.brevo_api_key and not self.mail_from_email:
            raise RuntimeError("MEDCHAIN_MAIL_FROM_EMAIL is required when MEDCHAIN_BREVO_API_KEY is set")

    @classmethod
    def from_env(cls) -> "Settings":
        cors = os.getenv("MEDCHAIN_CORS_ORIGINS")
        return cls(
            cors_origins=(
                tuple(item.strip() for item in cors.split(",") if item.strip())
                if cors
                else cls.cors_origins
            ),
            secret_key=os.getenv("MEDCHAIN_SECRET_KEY", ""),
            access_token_minutes=int(os.getenv("MEDCHAIN_ACCESS_TOKEN_MINUTES", "120")),
            refresh_token_days=int(os.getenv("MEDCHAIN_REFRESH_TOKEN_DAYS", str(cls.refresh_token_days))),
            invitation_expires_days=int(
                os.getenv("MEDCHAIN_INVITATION_EXPIRES_DAYS", str(cls.invitation_expires_days))
            ),
            reset_token_minutes=int(os.getenv("MEDCHAIN_RESET_TOKEN_MINUTES", str(cls.reset_token_minutes))),
            brevo_api_key=os.getenv("MEDCHAIN_BREVO_API_KEY"),
            mail_from_email=os.getenv("MEDCHAIN_MAIL_FROM_EMAIL"),
            mail_from_name=os.getenv("MEDCHAIN_MAIL_FROM_NAME", cls.mail_from_name),
            frontend_base_url=os.getenv("MEDCHAIN_FRONTEND_BASE_URL", cls.frontend_base_url),
            mongodb_uri=os.getenv("MEDCHAIN_MONGODB_URI"),
            mongodb_name=os.getenv("MEDCHAIN_MONGODB_NAME", cls.mongodb_name),
            azure_storage_connection_string=os.getenv("AZURE_STORAGE_CONNECTION_STRING"),
            azure_storage_account_url=os.getenv("AZURE_STORAGE_ACCOUNT_URL"),
            azure_storage_container=os.getenv("AZURE_STORAGE_CONTAINER"),
            chain_id=int(os.getenv("MEDCHAIN_CHAIN_ID", str(cls.chain_id))),
            chain_backend=os.getenv("MEDCHAIN_CHAIN_BACKEND", cls.chain_backend),
            signer_private_key=(
                os.getenv("MEDCHAIN_SIGNER_PRIVATE_KEY")
                or os.getenv("MEDCHAIN_EVM_SIGNER_PRIVATE_KEY")
            ),
            digital_twin_path=os.getenv("MEDCHAIN_DIGITAL_TWIN_PATH", cls.digital_twin_path),
            twin_floor_accuracy=float(os.getenv("MEDCHAIN_TWIN_FLOOR_ACCURACY", str(cls.twin_floor_accuracy))),
            twin_regression_tolerance=float(
                os.getenv("MEDCHAIN_TWIN_REGRESSION_TOLERANCE", str(cls.twin_regression_tolerance))
            ),
            anomaly_distance_cap=float(os.getenv("MEDCHAIN_ANOMALY_DISTANCE_CAP", str(cls.anomaly_distance_cap))),
            anomaly_mad_threshold=float(os.getenv("MEDCHAIN_ANOMALY_MAD_THRESHOLD", str(cls.anomaly_mad_threshold))),
            anomaly_cosine_threshold=float(
                os.getenv("MEDCHAIN_ANOMALY_COSINE_THRESHOLD", str(cls.anomaly_cosine_threshold))
            ),
            reported_metric_tolerance=float(
                os.getenv("MEDCHAIN_REPORTED_METRIC_TOLERANCE", str(cls.reported_metric_tolerance))
            ),
            reputation_reward=int(os.getenv("MEDCHAIN_REPUTATION_REWARD", str(cls.reputation_reward))),
            reputation_penalty=int(os.getenv("MEDCHAIN_REPUTATION_PENALTY", str(cls.reputation_penalty))),
            inference_low_confidence=float(
                os.getenv("MEDCHAIN_INFERENCE_LOW_CONFIDENCE", str(cls.inference_low_confidence))
            ),
            bootstrap_admin_email=os.getenv("MEDCHAIN_BOOTSTRAP_ADMIN_EMAIL"),
            bootstrap_admin_password=os.getenv("MEDCHAIN_BOOTSTRAP_ADMIN_PASSWORD"),
            bootstrap_admin_name=os.getenv("MEDCHAIN_BOOTSTRAP_ADMIN_NAME", cls.bootstrap_admin_name),
        )


settings = Settings.from_env()

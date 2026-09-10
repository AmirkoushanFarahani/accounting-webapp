from functools import lru_cache
from pathlib import Path

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application configuration loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_ENV: str = "development"
    APP_NAME: str = "Azari Intelligent Accounting"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str
    JWT_SECRET: SecretStr
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=5, le=1440)
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=30)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=30)
    DB_POOL_TIMEOUT_SECONDS: float = Field(default=2, gt=0, le=30)
    DB_CONNECT_TIMEOUT_SECONDS: int = Field(default=5, ge=1, le=30)
    DB_MAX_CONCURRENT_SESSIONS: int = Field(default=15, ge=1, le=32)
    DB_ADMISSION_TIMEOUT_SECONDS: float = Field(default=1, gt=0, le=10)
    AUTH_RATE_LIMIT_ATTEMPTS: int = Field(default=5, ge=1, le=100)
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=1, le=3600)
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:4173"])
    ML_MODEL_DIR: Path = Path("ml/models")
    ML_CONFIDENCE_THRESHOLD: float = Field(default=0.65, ge=0, le=1)
    BOOTSTRAP_ADMIN_EMAIL: EmailStr | None = None
    BOOTSTRAP_ADMIN_PASSWORD: SecretStr | None = None

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        return value

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        if value not in {"HS256", "HS384", "HS512"}:
            raise ValueError("JWT_ALGORITHM must be an HMAC SHA-2 algorithm")
        return value

    @field_validator("API_V1_PREFIX")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("API_V1_PREFIX must start, but not end, with '/'")
        return value

    @model_validator(mode="after")
    def validate_bootstrap_admin(self) -> "Settings":
        email_set = self.BOOTSTRAP_ADMIN_EMAIL is not None
        password_set = self.BOOTSTRAP_ADMIN_PASSWORD is not None
        if email_set != password_set:
            raise ValueError("Bootstrap administrator email and password must be set together")
        if self.BOOTSTRAP_ADMIN_PASSWORD is not None:
            password = self.BOOTSTRAP_ADMIN_PASSWORD.get_secret_value()
            if not 12 <= len(password) <= 128:
                raise ValueError("Bootstrap administrator password must be 12 to 128 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

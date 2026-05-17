from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    app_name: str = "BeeAGI Control Plane"
    app_version: str = "0.1.0"
    environment: str = "dev"
    control_plane_api_key: str | None = None
    control_plane_api_key_header: str = "X-API-Key"
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ]
    )
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True

    database_url: str = "sqlite:///./beeagi.db"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "minio123"
    artifact_dir: str = "./artifacts"

    local_model_endpoint: str = "http://127.0.0.1:11434"
    enterprise_model_endpoint: str = "https://enterprise-model-gateway.local"
    llm_mode: str = "mock"  # mock | ollama | openai_compatible | deepseek
    llm_timeout_seconds: int = 20
    llm_model_name: str = "qwen2.5:7b"
    llm_api_key: str | None = None
    deepseek_endpoint: str = "https://api.deepseek.com"
    deepseek_model_name: str = "deepseek-v4-flash"
    deepseek_api_key: str | None = None
    llm_runtime_config_path: str = "./artifacts/llm_runtime_config.json"

    celery_enabled: bool = False
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    shadow_improvement_threshold: float = 0.08
    canary_slice_ratio: float = 0.05
    canary_min_feedback_count: int = 3
    auto_rollback_quality_drop: float = 0.03
    auto_rollback_error_rise: float = 0.02

    scout_pheromone_ttl_hours: int = 48
    scout_pheromone_top_k: int = 5
    scout_pheromone_evaporation_rate: float = 0.06
    scout_pheromone_min_strength: float = 0.05
    scout_patrol_sample_size: int = 30

    autonomous_life_enabled: bool = True
    autonomous_life_min_interval_seconds: int = 6
    autonomous_life_idle_interval_seconds: int = 28
    autonomous_life_idle_after_seconds: int = 70
    autonomous_life_patrol_sample_active: int = 10
    autonomous_life_patrol_sample_idle: int = 4
    autonomous_life_self_evolution_enabled: bool = True
    autonomous_life_evolution_limit_active: int = 3
    autonomous_life_evolution_limit_idle: int = 1
    autonomous_life_auto_promote_enabled: bool = True
    autonomous_life_auto_promote_limit_active: int = 8
    autonomous_life_auto_promote_limit_idle: int = 3


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

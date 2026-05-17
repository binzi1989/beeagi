from datetime import datetime

from app.schemas.common import ApiModel


class LlmConfigView(ApiModel):
    llm_mode: str
    llm_model_name: str
    local_model_endpoint: str
    enterprise_model_endpoint: str
    deepseek_endpoint: str
    deepseek_model_name: str
    llm_timeout_seconds: int
    llm_api_key_configured: bool
    deepseek_api_key_configured: bool
    runtime_config_path: str


class LlmConfigUpdateRequest(ApiModel):
    llm_mode: str | None = None
    llm_model_name: str | None = None
    local_model_endpoint: str | None = None
    enterprise_model_endpoint: str | None = None
    deepseek_endpoint: str | None = None
    deepseek_model_name: str | None = None
    llm_timeout_seconds: int | None = None
    llm_api_key: str | None = None
    deepseek_api_key: str | None = None


class LlmTokenModelStat(ApiModel):
    provider: str
    model: str
    task_count: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    average_tokens: float


class LlmTokenTaskStat(ApiModel):
    task_id: str
    goal: str
    provider: str
    model: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    created_at: datetime


class LlmTokenStatsResponse(ApiModel):
    sample_size: int
    total_tasks: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    average_tokens_per_task: float
    by_model: list[LlmTokenModelStat]
    recent_tasks: list[LlmTokenTaskStat]

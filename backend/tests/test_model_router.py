from app.core.config import Settings
from app.services.model_router import ModelRouter


def test_model_router_deepseek_mode_uses_endpoint_and_key():
    settings = Settings(
        llm_mode="deepseek",
        deepseek_endpoint="https://api.deepseek.com",
        deepseek_model_name="deepseek-v4-flash",
        deepseek_api_key="deepseek-key",
        llm_runtime_config_path="./artifacts/test-model-router-no-file-1.json",
    )
    router = ModelRouter(settings)
    captured: dict[str, object] = {}

    def fake_post(url: str, payload: dict, api_key: str | None):
        captured["url"] = url
        captured["payload"] = payload
        captured["api_key"] = api_key
        return {
            "choices": [{"message": {"content": "deepseek ok"}}],
        }

    router._post_json = fake_post  # type: ignore[method-assign]
    result = router.generate("hello")

    assert result.provider == "deepseek"
    assert result.model == "deepseek-v4-flash"
    assert result.text == "deepseek ok"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["api_key"] == "deepseek-key"


def test_model_router_deepseek_key_fallback_to_llm_api_key():
    settings = Settings(
        llm_mode="deepseek",
        deepseek_endpoint="https://api.deepseek.com",
        deepseek_model_name="deepseek-v4-pro",
        llm_api_key="shared-key",
        deepseek_api_key=None,
        llm_runtime_config_path="./artifacts/test-model-router-no-file-2.json",
    )
    router = ModelRouter(settings)
    captured: dict[str, object] = {}

    def fake_post(url: str, payload: dict, api_key: str | None):
        captured["api_key"] = api_key
        return {
            "choices": [{"message": {"content": "fallback key ok"}}],
        }

    router._post_json = fake_post  # type: ignore[method-assign]
    result = router.generate("hello")

    assert result.provider == "deepseek"
    assert result.text == "fallback key ok"
    assert captured["api_key"] == "shared-key"

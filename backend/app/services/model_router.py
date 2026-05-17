from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from threading import RLock
from typing import Any
from urllib import error as url_error
from urllib import request as url_request

from app.core.config import Settings


@dataclass(slots=True)
class LlmResult:
    text: str
    provider: str
    model: str
    raw: dict[str, Any]


class ModelRouter:
    _allowed_runtime_fields = {
        "llm_mode",
        "llm_model_name",
        "local_model_endpoint",
        "enterprise_model_endpoint",
        "deepseek_endpoint",
        "deepseek_model_name",
        "llm_timeout_seconds",
        "llm_api_key",
        "deepseek_api_key",
    }
    _allowed_modes = {"mock", "ollama", "openai_compatible", "deepseek"}

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = RLock()
        self._runtime_config_path = Path(settings.llm_runtime_config_path)
        self._overrides: dict[str, Any] = {}
        self._load_runtime_config()

    def _load_runtime_config(self) -> None:
        with self._lock:
            path = self._runtime_config_path
            if not path.exists():
                return
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return
            if isinstance(payload, dict):
                for key, value in payload.items():
                    if key in self._allowed_runtime_fields:
                        self._overrides[key] = value

    def _save_runtime_config(self) -> None:
        with self._lock:
            path = self._runtime_config_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._overrides, ensure_ascii=False, indent=2), encoding="utf-8")

    def _resolved(self, key: str) -> Any:
        with self._lock:
            if key in self._overrides:
                return self._overrides[key]
        return getattr(self.settings, key)

    def _build_runtime_view(self) -> dict[str, Any]:
        return {
            "llmMode": str(self._resolved("llm_mode")),
            "llmModelName": str(self._resolved("llm_model_name")),
            "localModelEndpoint": str(self._resolved("local_model_endpoint")),
            "enterpriseModelEndpoint": str(self._resolved("enterprise_model_endpoint")),
            "deepseekEndpoint": str(self._resolved("deepseek_endpoint")),
            "deepseekModelName": str(self._resolved("deepseek_model_name")),
            "llmTimeoutSeconds": int(self._resolved("llm_timeout_seconds")),
            "llmApiKeyConfigured": bool(self._resolved("llm_api_key")),
            "deepseekApiKeyConfigured": bool(self._resolved("deepseek_api_key") or self._resolved("llm_api_key")),
            "runtimeConfigPath": str(self._runtime_config_path),
        }

    def get_runtime_config(self) -> dict[str, Any]:
        with self._lock:
            return self._build_runtime_view()

    def update_runtime_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for key, raw_value in patch.items():
                if key not in self._allowed_runtime_fields:
                    continue
                if key == "llm_mode":
                    mode = str(raw_value).strip().lower()
                    if mode not in self._allowed_modes:
                        raise ValueError(f"unsupported llm_mode: {mode}")
                    self._overrides[key] = mode
                    continue
                if key == "llm_timeout_seconds":
                    timeout = int(raw_value)
                    if timeout < 1 or timeout > 120:
                        raise ValueError("llm_timeout_seconds must be between 1 and 120")
                    self._overrides[key] = timeout
                    continue
                if key in {"llm_api_key", "deepseek_api_key"}:
                    value = str(raw_value or "").strip()
                    if value:
                        self._overrides[key] = value
                    else:
                        self._overrides.pop(key, None)
                    continue

                value = str(raw_value).strip()
                if not value:
                    raise ValueError(f"{key} cannot be empty")
                self._overrides[key] = value

            self._save_runtime_config()
            return self._build_runtime_view()

    def generate(self, prompt: str) -> LlmResult:
        mode = str(self._resolved("llm_mode")).strip().lower()
        if mode == "ollama":
            return self._call_ollama(prompt)
        if mode == "deepseek":
            return self._call_deepseek(prompt)
        if mode == "openai_compatible":
            return self._call_openai_compatible(prompt)
        return self._mock(prompt)

    def _mock(self, prompt: str) -> LlmResult:
        text = (
            "LLM(mock) summary: task executed via deterministic path. "
            "To enable real LLM output, set APP_LLM_MODE=ollama/deepseek/openai_compatible."
        )
        return LlmResult(text=text, provider="mock", model="mock-model", raw={"promptSize": len(prompt)})

    def _call_ollama(self, prompt: str) -> LlmResult:
        endpoint = str(self._resolved("local_model_endpoint")).rstrip("/") + "/api/generate"
        model_name = str(self._resolved("llm_model_name"))
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
        }
        resp = self._post_json(endpoint, payload, api_key=None)
        text = str(resp.get("response", "")).strip()
        if not text:
            text = "Ollama returned empty response."
        return LlmResult(text=text, provider="ollama", model=model_name, raw=resp)

    def _call_openai_compatible(self, prompt: str) -> LlmResult:
        endpoint = str(self._resolved("enterprise_model_endpoint")).rstrip("/") + "/v1/chat/completions"
        model_name = str(self._resolved("llm_model_name"))
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are an execution summarizer for BeeAGI."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        api_key = self._resolved("llm_api_key")
        resp = self._post_json(endpoint, payload, api_key=api_key)
        text = ""
        choices = resp.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            text = str(message.get("content", "")).strip()
        if not text:
            text = "Gateway returned empty response."
        return LlmResult(text=text, provider="openai_compatible", model=model_name, raw=resp)

    def _call_deepseek(self, prompt: str) -> LlmResult:
        endpoint = str(self._resolved("deepseek_endpoint")).rstrip("/") + "/chat/completions"
        model_name = str(self._resolved("deepseek_model_name"))
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are an execution summarizer for BeeAGI."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        api_key = self._resolved("deepseek_api_key") or self._resolved("llm_api_key")
        resp = self._post_json(endpoint, payload, api_key=api_key)
        text = ""
        choices = resp.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            text = str(message.get("content", "")).strip()
        if not text:
            text = "DeepSeek returned empty response."
        return LlmResult(text=text, provider="deepseek", model=model_name, raw=resp)

    def _post_json(self, url: str, payload: dict[str, Any], api_key: str | None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = url_request.Request(url=url, data=body, headers=headers, method="POST")
        timeout_seconds = int(self._resolved("llm_timeout_seconds"))
        try:
            with url_request.urlopen(req, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except url_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"LLM HTTPError {exc.code}: {detail}") from exc
        except url_error.URLError as exc:
            raise RuntimeError(f"LLM connection failed: {exc.reason}") from exc

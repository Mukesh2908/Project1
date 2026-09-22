"""The single door every LLM call goes through — project.md 19.1 and 20.1.

The allowlist check happens **before** the request is built. A blocked provider
raises; there is no override flag, and no UI path around it. Switching a
profile from fixture to real data therefore cannot quietly widen where its text
goes (decision D12).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import API_KEY_ENV, PROVIDERS, load_settings, provider_of, text_hash

T = TypeVar("T", bound=BaseModel)


class ProviderBlockedError(RuntimeError):
    """Raised when privacy mode forbids the requested provider."""


class ProviderUnavailableError(RuntimeError):
    """Raised when every configured provider and fallback failed."""


def check_allowed(model: str, settings: dict | None = None, real_data: bool = False) -> None:
    """Enforce the privacy mode. Call this before building any request.

    ``dummy_data_only`` permits anything, because no real profile text is in
    play. ``approved_cloud`` permits only providers the company has approved for
    employee data.
    """
    settings = settings or load_settings()
    privacy = settings.get("privacy", {})
    mode = privacy.get("mode", "dummy_data_only")
    provider = provider_of(model)

    if provider == "mock":
        return

    if mode == "dummy_data_only":
        if real_data:
            raise ProviderBlockedError(
                "privacy.mode is 'dummy_data_only', which forbids sending real profile "
                "data to any provider. Switch to 'approved_cloud' and list the approved "
                "providers once your company has signed off."
            )
        return

    if mode == "approved_cloud":
        approved = set(privacy.get("approved_providers") or [])
        if provider not in approved:
            raise ProviderBlockedError(
                f"Provider '{provider}' is not in privacy.approved_providers "
                f"({sorted(approved) or 'empty'}). Real profile data may only go to "
                "providers approved for employee data."
            )
        return

    raise ProviderBlockedError(f"Unknown privacy mode: {mode!r}")


@dataclass
class CallRecord:
    """What every stored LLM output carries — project.md 19.1."""

    model: str
    prompt_version: str
    input_hash: str
    cached: bool = False
    attempts: int = 1


class AIProvider:
    """Interface: ``extract(schema, prompt)`` returns a validated model."""

    name = "base"

    def extract(
        self,
        schema: type[T],
        prompt: str,
        *,
        model: str,
        prompt_version: str = "v1",
        real_data: bool = False,
    ) -> tuple[T, CallRecord]:
        raise NotImplementedError


@dataclass
class MockProvider(AIProvider):
    """Deterministic fixtures for tests and offline development.

    Responses are keyed by schema name; anything unregistered raises, so a test
    can never accidentally depend on a live model.
    """

    name: str = "mock"
    responses: dict[str, Any] = field(default_factory=dict)
    calls: list[CallRecord] = field(default_factory=list)

    def register(self, schema: type[BaseModel], payload: Any) -> None:
        self.responses[schema.__name__] = payload

    def extract(
        self,
        schema: type[T],
        prompt: str,
        *,
        model: str = "mock/fixture",
        prompt_version: str = "v1",
        real_data: bool = False,
    ) -> tuple[T, CallRecord]:
        check_allowed(model, real_data=real_data)
        key = schema.__name__
        if key not in self.responses:
            raise ProviderUnavailableError(
                f"MockProvider has no registered response for {key}. "
                "Register one rather than falling back to a live model."
            )
        payload = self.responses[key]
        if callable(payload):
            payload = payload(prompt)
        record = CallRecord(
            model=model, prompt_version=prompt_version, input_hash=text_hash(prompt)
        )
        self.calls.append(record)
        if isinstance(payload, schema):
            return payload, record
        return schema.model_validate(payload), record


@dataclass
class LiteLLMProvider(AIProvider):
    """Gemini, Groq, NVIDIA NIM and OpenAI, behind one call.

    LiteLLM and Instructor are optional dependencies: the app imports and tests
    cleanly without them, and only a real call requires them to be installed.
    """

    name: str = "litellm"
    cache: dict[str, Any] = field(default_factory=dict)
    calls: list[CallRecord] = field(default_factory=list)

    def extract(
        self,
        schema: type[T],
        prompt: str,
        *,
        model: str,
        prompt_version: str = "v1",
        real_data: bool = False,
    ) -> tuple[T, CallRecord]:
        check_allowed(model, real_data=real_data)
        settings = load_settings()
        llm = settings.get("llm", {})
        key = text_hash(f"{model}|{prompt_version}|{prompt}")

        if key in self.cache:
            record = CallRecord(
                model=model, prompt_version=prompt_version, input_hash=key, cached=True
            )
            self.calls.append(record)
            return schema.model_validate(self.cache[key]), record

        candidates = [model] + list(llm.get("fallbacks") or [])
        max_retries = int(llm.get("max_retries", 3))
        temperature = float(llm.get("temperature", 0.0))
        last_error: Exception | None = None

        for candidate in candidates:
            try:
                check_allowed(candidate, settings, real_data=real_data)
            except ProviderBlockedError as exc:
                last_error = exc
                continue
            if not _has_key(candidate):
                last_error = ProviderUnavailableError(
                    f"No API key for {provider_of(candidate)} "
                    f"(set {API_KEY_ENV.get(provider_of(candidate), 'the API key')})"
                )
                continue
            for attempt in range(1, max_retries + 1):
                try:
                    payload = self._call(schema, prompt, candidate, temperature)
                    self.cache[key] = payload
                    record = CallRecord(
                        model=candidate,
                        prompt_version=prompt_version,
                        input_hash=key,
                        attempts=attempt,
                    )
                    self.calls.append(record)
                    return schema.model_validate(payload), record
                except ValidationError as exc:
                    last_error = exc
                    prompt = f"{prompt}\n\nThe previous reply was not valid JSON for the schema. Return only valid JSON."
                except Exception as exc:  # noqa: BLE001 - provider errors vary widely
                    last_error = exc
                    time.sleep(min(2**attempt, 8))
        raise ProviderUnavailableError(
            f"All providers failed for {model}. Last error: {last_error}"
        )

    def _call(self, schema: type[T], prompt: str, model: str, temperature: float) -> Any:
        try:
            import instructor
            import litellm
        except ImportError as exc:  # pragma: no cover - exercised only with extras
            raise ProviderUnavailableError(
                "litellm and instructor are required for live calls: pip install '.[llm]'"
            ) from exc

        client = instructor.from_litellm(litellm.completion)
        result = client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_model=schema,
            messages=[{"role": "user", "content": prompt}],
        )
        return json.loads(result.model_dump_json())


def _has_key(model: str) -> bool:
    import os

    provider = provider_of(model)
    env = API_KEY_ENV.get(provider)
    return bool(env and os.environ.get(env))


def available_providers() -> dict[str, dict]:
    """What Settings shows: configured, keyed, and whether the free tier trains."""
    import os

    out: dict[str, dict] = {}
    for provider, meta in PROVIDERS.items():
        env = API_KEY_ENV.get(provider)
        out[provider] = {
            **meta,
            "env_var": env,
            "key_present": bool(env and os.environ.get(env)) or provider == "mock",
        }
    return out


def default_provider() -> AIProvider:
    return LiteLLMProvider()

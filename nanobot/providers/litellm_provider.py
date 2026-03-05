"""LiteLLM provider implementation for multi-provider support."""

import json_repair
import os
import secrets
import string
from typing import Any

import httpx

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from nanobot.providers.registry import find_by_model, find_gateway


# Standard OpenAI chat-completion message keys plus reasoning_content for
# thinking-enabled models (Kimi k2.5, DeepSeek-R1, etc.).
_ALLOWED_MSG_KEYS = frozenset({"role", "content", "tool_calls", "tool_call_id", "name", "reasoning_content", "thinking_blocks"})
_ALNUM = string.ascii_letters + string.digits

def _short_tool_id() -> str:
    """Generate a 9-char alphanumeric ID compatible with all providers (incl. Mistral)."""
    return "".join(secrets.choice(_ALNUM) for _ in range(9))


class LiteLLMProvider(LLMProvider):
    """
    LLM provider using LiteLLM for multi-provider support.
    
    Supports OpenRouter, Anthropic, OpenAI, Gemini, MiniMax, and many other providers through
    a unified interface.  Provider-specific logic is driven by the registry
    (see providers/registry.py) — no if-elif chains needed here.
    """
    
    def __init__(
        self, 
        api_key: str | None = None, 
        api_base: str | None = None,
        proxy: str | None = None,
        default_model: str = "google/gemini-3.1-flash-lite-preview",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.proxy = proxy
        self.extra_headers = extra_headers or {}
        
        # Detect gateway / local deployment.
        # provider_name (from config key) is the primary signal;
        # api_key / api_base are fallback for auto-detection.
        self._gateway = find_gateway(provider_name, api_key, api_base)
        
        # Configure environment variables
        if api_key:
            self._setup_env(api_key, api_base, default_model)

        if proxy:
            self._setup_proxy_env(proxy)
        self._litellm = None
        self._acompletion = None

    @staticmethod
    def _setup_proxy_env(proxy: str) -> None:
        """Configure process-level HTTP proxy for SDK/network clients."""
        proxy = proxy.strip()
        if not proxy:
            return
        for env_name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
            os.environ[env_name] = proxy
    
    def _setup_env(self, api_key: str, api_base: str | None, model: str) -> None:
        """Set environment variables based on detected provider."""
        spec = self._gateway or find_by_model(model)
        if not spec:
            return
        if not spec.env_key:
            # Provider specs without env key are ignored.
            return

        # Gateway/local overrides existing env; standard provider doesn't
        if self._gateway:
            os.environ[spec.env_key] = api_key
        else:
            os.environ.setdefault(spec.env_key, api_key)

        # Resolve env_extras placeholders:
        #   {api_key}  → user's API key
        #   {api_base} → user's api_base, falling back to spec.default_api_base
        effective_base = api_base or spec.default_api_base
        for env_name, env_val in spec.env_extras:
            resolved = env_val.replace("{api_key}", api_key)
            resolved = resolved.replace("{api_base}", effective_base)
            os.environ.setdefault(env_name, resolved)
    
    def _resolve_model(self, model: str) -> str:
        """Resolve model name by applying provider/gateway prefixes."""
        if self._gateway:
            # Gateway mode: apply gateway prefix, skip provider-specific prefixes
            prefix = self._gateway.litellm_prefix
            if self._gateway.strip_model_prefix:
                model = model.split("/")[-1]
            if prefix and not model.startswith(f"{prefix}/"):
                model = f"{prefix}/{model}"
            return model
        
        # Standard mode: auto-prefix for known providers
        spec = find_by_model(model)
        if spec and spec.litellm_prefix:
            model = self._canonicalize_explicit_prefix(model, spec.name, spec.litellm_prefix)
            if not any(model.startswith(s) for s in spec.skip_prefixes):
                model = f"{spec.litellm_prefix}/{model}"

        return model

    @staticmethod
    def _canonicalize_explicit_prefix(model: str, spec_name: str, canonical_prefix: str) -> str:
        """Normalize explicit provider prefixes like `openrouter/...`."""
        if "/" not in model:
            return model
        prefix, remainder = model.split("/", 1)
        if prefix.lower().replace("-", "_") != spec_name:
            return model
        return f"{canonical_prefix}/{remainder}"
    
    def _supports_cache_control(self, model: str) -> bool:
        """Return True when the provider supports cache_control on content blocks."""
        if self._gateway is not None:
            return self._gateway.supports_prompt_caching
        spec = find_by_model(model)
        return spec is not None and spec.supports_prompt_caching

    def _apply_cache_control(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
        """Return copies of messages and tools with cache_control injected."""
        new_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                content = msg["content"]
                if isinstance(content, str):
                    new_content = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
                else:
                    new_content = list(content)
                    new_content[-1] = {**new_content[-1], "cache_control": {"type": "ephemeral"}}
                new_messages.append({**msg, "content": new_content})
            else:
                new_messages.append(msg)

        new_tools = tools
        if tools:
            new_tools = list(tools)
            new_tools[-1] = {**new_tools[-1], "cache_control": {"type": "ephemeral"}}

        return new_messages, new_tools

    def _apply_model_overrides(self, model: str, kwargs: dict[str, Any]) -> None:
        """Apply model-specific parameter overrides from the registry."""
        model_lower = model.lower()
        spec = find_by_model(model)
        if spec:
            for pattern, overrides in spec.model_overrides:
                if pattern in model_lower:
                    kwargs.update(overrides)
                    return
    
    @staticmethod
    def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Strip non-standard keys and ensure assistant messages have a content key."""
        sanitized = []
        for msg in messages:
            clean = {k: v for k, v in msg.items() if k in _ALLOWED_MSG_KEYS}
            # Strict providers require "content" even when assistant only has tool_calls
            if clean.get("role") == "assistant" and "content" not in clean:
                clean["content"] = None
            sanitized.append(clean)
        return sanitized

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """
        Send a chat completion request via LiteLLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions in OpenAI format.
            model: Model identifier (e.g., 'anthropic/claude-sonnet-4-5').
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
        
        Returns:
            LLMResponse with content and/or tool calls.
        """
        if self._gateway and self._gateway.name == "openrouter":
            return await self._chat_openrouter_direct(
                messages=messages,
                tools=tools,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            )

        return await self._chat_litellm(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

    async def _chat_openrouter_direct(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """Fast path for OpenRouter without importing LiteLLM."""
        original_model = model or self.default_model
        resolved_model = self._resolve_openrouter_model(original_model)

        if self._supports_cache_control(original_model):
            messages, tools = self._apply_cache_control(messages, tools)

        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": self._sanitize_messages(self._sanitize_empty_content(messages)),
            "max_tokens": max(1, max_tokens),
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if reasoning_effort:
            # OpenRouter forwards this to compatible models; unsupported models ignore/reject.
            payload["reasoning_effort"] = reasoning_effort

        if not self.api_key:
            return LLMResponse(content="Error calling LLM: missing API key", finish_reason="error")

        base = (self.api_base or (self._gateway.default_api_base if self._gateway else "")).rstrip("/")
        if not base:
            base = "https://openrouter.ai/api/v1"
        url = f"{base}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

        try:
            async with httpx.AsyncClient(proxy=self.proxy, timeout=httpx.Timeout(60.0)) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
            return self._parse_response(response.json())
        except Exception as e:
            return LLMResponse(
                content=f"Error calling LLM: {str(e)}",
                finish_reason="error",
            )

    async def _chat_litellm(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """Compatibility path for non-OpenRouter providers via LiteLLM."""
        original_model = model or self.default_model
        model = self._resolve_model(original_model)

        if self._supports_cache_control(original_model):
            messages, tools = self._apply_cache_control(messages, tools)

        # Clamp max_tokens to at least 1 — negative or zero values cause
        # LiteLLM to reject the request with "max_tokens must be at least 1".
        max_tokens = max(1, max_tokens)
        
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._sanitize_messages(self._sanitize_empty_content(messages)),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        # Apply model-specific overrides (e.g. kimi-k2.5 temperature)
        self._apply_model_overrides(model, kwargs)
        
        # Pass api_key directly — more reliable than env vars alone
        if self.api_key:
            kwargs["api_key"] = self.api_key
        
        # Pass api_base override when configured
        if self.api_base:
            kwargs["api_base"] = self.api_base
        
        # Pass extra headers (e.g. APP-Code for AiHubMix)
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers
        
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
            kwargs["drop_params"] = True
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            litellm, acompletion = self._load_litellm()
            if self.api_base:
                litellm.api_base = self.api_base
            # Disable LiteLLM logging noise
            litellm.suppress_debug_info = True
            # Drop unsupported parameters for providers (e.g., gpt-5 rejects some params)
            litellm.drop_params = True
            response = await acompletion(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            # Return error as content for graceful handling
            return LLMResponse(
                content=f"Error calling LLM: {str(e)}",
                finish_reason="error",
            )

    @staticmethod
    def _pick(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _load_litellm(self):
        """Lazy import to keep CLI startup fast for OpenRouter direct mode."""
        if self._litellm is None or self._acompletion is None:
            import litellm
            from litellm import acompletion

            self._litellm = litellm
            self._acompletion = acompletion
        return self._litellm, self._acompletion

    @staticmethod
    def _resolve_openrouter_model(model: str) -> str:
        """OpenRouter API expects raw model names, without `openrouter/` prefix."""
        return model.split("/", 1)[1] if model.startswith("openrouter/") else model

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse LiteLLM/OpenRouter response into our standard format."""
        choices = self._pick(response, "choices", []) or []
        if not choices:
            return LLMResponse(content=None, finish_reason="error")

        choice = choices[0]
        message = self._pick(choice, "message", {}) or {}
        content = self._pick(message, "content") or self._pick(message, "refusal")

        tool_calls = []
        raw_tool_calls = self._pick(message, "tool_calls", []) or []
        if raw_tool_calls:
            for tc in raw_tool_calls:
                function = self._pick(tc, "function", {}) or {}
                # Parse arguments from JSON string if needed
                args = self._pick(function, "arguments", {})
                if isinstance(args, str):
                    try:
                        args = json_repair.loads(args)
                    except Exception:
                        args = {}
                if not isinstance(args, dict):
                    args = {}

                tool_calls.append(ToolCallRequest(
                    id=self._pick(tc, "id", _short_tool_id()),
                    name=self._pick(function, "name", ""),
                    arguments=args,
                ))

        usage = {}
        usage_obj = self._pick(response, "usage")
        if usage_obj:
            usage = {
                "prompt_tokens": self._pick(usage_obj, "prompt_tokens", 0),
                "completion_tokens": self._pick(usage_obj, "completion_tokens", 0),
                "total_tokens": self._pick(usage_obj, "total_tokens", 0),
            }

        reasoning_content = self._pick(message, "reasoning_content", None) or None
        thinking_blocks = self._pick(message, "thinking_blocks", None) or None

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=self._pick(choice, "finish_reason", "stop") or "stop",
            usage=usage,
            reasoning_content=reasoning_content,
            thinking_blocks=thinking_blocks,
        )
    
    def get_default_model(self) -> str:
        """Get the default model."""
        return self.default_model

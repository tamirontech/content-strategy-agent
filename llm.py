"""
Unified LLM interface supporting Anthropic and Ollama providers.

Configured via environment variables (overridable via CLI flags):
  LLM_PROVIDER   anthropic (default) | ollama
  LLM_MODEL      claude-opus-4-6 (default for anthropic) | llama3.2 (default for ollama)
  OLLAMA_HOST    http://localhost:11434 (default)
"""

import os

# Lazy-initialised clients — only imported/created when actually used
_anthropic_sync = None
_anthropic_async = None


def _sync_client():
    global _anthropic_sync
    if _anthropic_sync is None:
        import anthropic
        _anthropic_sync = anthropic.Anthropic()
    return _anthropic_sync


def _async_client():
    global _anthropic_async
    if _anthropic_async is None:
        import anthropic
        _anthropic_async = anthropic.AsyncAnthropic()
    return _anthropic_async


def get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "anthropic").lower()


def get_model() -> str:
    provider = get_provider()
    if provider == "ollama":
        return os.getenv("LLM_MODEL", "llama3.2")
    return os.getenv("LLM_MODEL", "claude-opus-4-6")


def provider_label() -> str:
    """Human-readable label for display."""
    return f"{get_provider()} / {get_model()}"


def _supports_thinking(model: str) -> bool:
    """Adaptive thinking is only available on Opus and Sonnet 4.x+."""
    return not model.startswith("claude-haiku")


# ── Synchronous (used by agent.py, brief_generator.py) ────────────────────────

def complete(
    messages: list,
    system: str = None,
    max_tokens: int = 4000,
    json_mode: bool = False,
) -> str:
    """
    Synchronous LLM completion. Returns the full response text.

    json_mode=True tells Ollama to constrain output to valid JSON.
    Ignored for Anthropic (the prompt handles it).
    """
    provider = get_provider()
    model = get_model()

    if provider == "anthropic":
        kwargs = dict(model=model, max_tokens=max_tokens, messages=messages)
        if system:
            kwargs["system"] = system
        if _supports_thinking(model):
            kwargs["thinking"] = {"type": "adaptive"}
        with _sync_client().messages.stream(**kwargs) as stream:
            return "".join(stream.text_stream)

    elif provider == "ollama":
        import ollama
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        client = ollama.Client(host=host)

        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        kwargs = dict(model=model, messages=msgs)
        if json_mode:
            kwargs["format"] = "json"

        resp = client.chat(**kwargs)
        return resp.message.content

    else:
        raise ValueError(f"Unknown provider '{provider}'. Use 'anthropic' or 'ollama'.")


# ── Asynchronous (used by article_writer.py) ──────────────────────────────────

async def async_complete(
    messages: list,
    system: str = None,
    max_tokens: int = 8000,
) -> str:
    """
    Asynchronous streaming LLM completion. Returns the full response text.
    """
    provider = get_provider()
    model = get_model()

    if provider == "anthropic":
        kwargs = dict(model=model, max_tokens=max_tokens, messages=messages)
        if system:
            kwargs["system"] = system
        if _supports_thinking(model):
            kwargs["thinking"] = {"type": "adaptive"}
        content = ""
        async with _async_client().messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                content += text
        return content

    elif provider == "ollama":
        import ollama
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        client = ollama.AsyncClient(host=host)

        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        content = ""
        async for chunk in await client.chat(model=model, messages=msgs, stream=True):
            content += chunk.message.content
        return content

    else:
        raise ValueError(f"Unknown provider '{provider}'. Use 'anthropic' or 'ollama'.")

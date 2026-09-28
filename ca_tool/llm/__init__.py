from .base import LLM, LLMError


def get_llm(engine: str = "gemini") -> LLM:
    """Factory: the only place that knows which engine is in use."""
    if engine == "gemini":
        from .gemini import GeminiLLM
        return GeminiLLM()
    raise LLMError(f"unknown engine: {engine}")


__all__ = ["LLM", "LLMError", "get_llm"]

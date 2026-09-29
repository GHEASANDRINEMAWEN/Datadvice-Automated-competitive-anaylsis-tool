"""Gemini engine. Retries transient errors and falls back down the configured model list."""
from __future__ import annotations

import logging
import time

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from .. import config
from .base import LLM, LLMError, T

log = logging.getLogger(__name__)

# 429 = quota/rate, 503 = overloaded, 500 = transient; 404 = model retired for this key
_RETRYABLE = {429, 500, 503}


class GeminiLLM(LLM):
    name = "gemini"

    def __init__(self, api_key: str = "", models: list[str] | None = None, retries: int = 3,
                 rounds: int = 2, round_wait: int = 25):
        self.rounds, self.round_wait = rounds, round_wait
        key = api_key or config.GEMINI_API_KEY
        if not key:
            raise LLMError("GEMINI_API_KEY is not set (see .env.example)")
        # without a timeout an overloaded model can hang a run indefinitely
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=config.LLM_TIMEOUT * 1000))
        self.models = models or config.GEMINI_MODELS
        self.retries = retries
        self.last_model = ""

    # model -> unix time until which it is skipped (shared across instances)
    _cooldown: dict[str, float] = {}

    def _call(self, prompt: str, cfg: types.GenerateContentConfig) -> str:
        """Try each live model; if every one is temporarily busy (429/503/timeout), wait and make
        one more full pass ignoring cooldowns, since free-tier availability changes by the minute."""
        for rnd in range(self.rounds):
            if rnd:
                log.warning("all models busy; waiting %ss before a final attempt", self.round_wait)
                time.sleep(self.round_wait)
                live = [m for m in self.models if self._cooldown.get(m, 0) - time.time() < 3000]  # skip retired (404) models
            else:
                live = [m for m in self.models if self._cooldown.get(m, 0) < time.time()] or self.models
            try:
                return self._pass(prompt, cfg, live)
            except LLMError as e:
                last = e
                if not getattr(e, "transient", False):
                    break  # waiting only helps when models were busy, not for bad requests/empty replies
        raise last

    def _pass(self, prompt: str, cfg: types.GenerateContentConfig, live: list[str]) -> str:
        last_err: Exception | None = None
        transient = False
        for model in live:
            for attempt in range(self.retries):
                try:
                    r = self.client.models.generate_content(model=model, contents=prompt, config=cfg)
                    text = "".join(p.text for p in (r.candidates[0].content.parts or []) if getattr(p, "text", None)) if r.candidates else ""
                    if not text:
                        # empty/blocked reply: deterministic for this prompt+model, so no retry here
                        last_err = LLMError(f"empty or blocked response from {model}")
                        break
                    self.last_model = model
                    return text
                except errors.APIError as e:
                    last_err = e
                    if e.code in (401, 403):
                        raise LLMError(f"the API key was refused ({e.code}); check GEMINI_API_KEY") from e
                    if e.code == 404:
                        log.warning("model %s not available to this key; skipping it for an hour", model)
                        self._cooldown[model] = time.time() + 3600
                        break
                    if e.code not in _RETRYABLE:
                        # e.g. 400 for this particular prompt: try the next model, but don't bench this one
                        log.warning("model %s rejected the request (%s); trying next", model, e.code)
                        break
                    transient = True
                    if attempt == self.retries - 1 or (e.code == 429 and attempt >= 1):
                        # skip this model for a while instead of re-paying the retries on every call
                        self._cooldown[model] = time.time() + (300 if e.code == 429 else 120)
                        log.warning("model %s cooling down after %s", model, e.code)
                        break
                    time.sleep(2 * (attempt + 1))
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    last_err, transient = e, True
                    self._cooldown[model] = time.time() + 300
                    log.warning("model %s timed out; cooling down", model)
                    break
        err = LLMError(f"all models failed: {last_err}")
        err.transient = transient
        raise err

    def generate_text(self, prompt: str, system: str = "") -> str:
        cfg = types.GenerateContentConfig(system_instruction=system or None, temperature=0.2)
        return self._call(prompt, cfg)

    def generate_json(self, prompt: str, schema: type[T], system: str = "") -> T:
        cfg = types.GenerateContentConfig(
            system_instruction=system or None,
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=schema,
        )
        text = self._call(prompt, cfg)
        try:
            return schema.model_validate_json(text)
        except ValidationError:
            # one repair attempt: ask again, showing the validation target
            text = self._call(prompt + "\n\nReturn ONLY valid JSON matching the schema.", cfg)
            try:
                return schema.model_validate_json(text)
            except ValidationError as e:  # callers (and the app) handle LLMError, not pydantic errors
                raise LLMError(f"the model returned malformed data twice ({schema.__name__}): {str(e)[:200]}") from e

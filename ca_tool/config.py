"""Runtime configuration, read from environment / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS", "gemini-3.6-flash,gemini-3.7-flash,gemini-3.5-flash,gemini-3.1-flash-lite,gemini-flash-lite-latest").split(",") if m.strip()]
PROJECTS_DIR = ROOT / os.getenv("CA_PROJECTS_DIR", "projects")

# Research limits (keep prompts within free-tier token budgets)
MAX_PAGE_CHARS = int(os.getenv("CA_MAX_PAGE_CHARS", "6000"))
MAX_SNIPPET_CHARS = int(os.getenv("CA_MAX_SNIPPET_CHARS", "30000"))  # search-result bundles
MAX_CORPUS_CHARS = int(os.getenv("CA_MAX_CORPUS_CHARS", "140000"))
HTTP_TIMEOUT = int(os.getenv("CA_HTTP_TIMEOUT", "20"))
LLM_TIMEOUT = int(os.getenv("CA_LLM_TIMEOUT", "180"))  # seconds per model call

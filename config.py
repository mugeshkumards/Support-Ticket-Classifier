import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter exposes an OpenAI-compatible API at this base URL.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Optional headers OpenRouter uses for analytics / leaderboards.
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "support-ticket-classifier")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost")

# Model slugs are in `<provider>/<model>` form on OpenRouter.
# Pick any models you have credit for; these defaults are cheap + reliable.
PRIMARY_MODEL = "openai/gpt-4o-mini"
FALLBACK_MODEL = "anthropic/claude-3.5-sonnet"

# Pricing in USD per 1,000,000 tokens. Update from
# https://openrouter.ai/models if these drift.
MODEL_PRICING = {
    "openai/gpt-4o-mini":         {"input": 0.15, "output": 0.60},
    "openai/gpt-4o":              {"input": 2.50, "output": 10.00},
    "anthropic/claude-3.5-haiku": {"input": 0.80, "output": 4.00},
    "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "anthropic/claude-3-opus":    {"input": 15.00, "output": 75.00},
    "google/gemini-2.5-flash":    {"input": 0.30, "output": 2.50},
    "meta-llama/llama-3.3-70b-instruct": {"input": 0.13, "output": 0.40},
}

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
MIN_CONFIDENCE_THRESHOLD = 0.6

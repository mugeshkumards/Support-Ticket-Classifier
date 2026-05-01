# 🤖 AI-Powered Support Ticket Classifier

> **Project 01 — LLM Engineering | Agentic AI**

[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-Render-4c51bf?style=for-the-badge)](https://support-ticket-classifier-jtu5.onrender.com)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-181717?style=for-the-badge&logo=github)](https://github.com/mugeshkumards/Support-Ticket-Classifier)
[![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![OpenAI](https://img.shields.io/badge/OpenAI_API-Compatible-412991?style=for-the-badge&logo=openai&logoColor=white)](https://openrouter.ai)

---

## 📋 Resume Project Summary

> **AI-Powered Support Ticket Classifier** — An end-to-end LLM-based system that automatically classifies e-commerce support tickets into actionable categories with PII redaction, cost tracking, and agentic fallback.

### 🎯 Key Highlights (for Resume / Portfolio)

- **Built a production-grade AI classification pipeline** using OpenAI-compatible APIs (via OpenRouter) with structured tool-calling to auto-categorize support tickets by category, priority, sentiment, and team routing
- **Implemented agentic fallback architecture** — primary model (GPT-4o Mini) automatically escalates to a stronger model (Claude 3.5 Sonnet) when classification confidence drops below threshold
- **Designed PII redaction engine** using regex + Luhn algorithm to detect and mask emails, phone numbers, credit cards, SSNs, and IP addresses before sending data to LLMs
- **Engineered structured output with Pydantic validation** — enforced enum-constrained schemas with business-rule validation ensuring 100% type-safe, downstream-ready JSON responses
- **Built real-time cost tracking system** calculating per-call USD costs across multiple model tiers with aggregate reporting
- **Developed premium glassmorphism Web UI** with Flask backend — includes sample ticket chips, confidence bars, sentiment badges, and smart alerts for low-confidence and prompt injection detection
- **Deployed on Render** with Gunicorn for production-ready serving

### 🛠️ Tech Stack

`Python` · `OpenAI API` · `OpenRouter` · `Pydantic` · `Flask` · `Gunicorn` · `HTML/CSS/JS` · `Render`

---

## ✨ Features

| Feature | Description |
| --- | --- |
| 🏷️ **Multi-label Classification** | Category, team routing, priority, sentiment — all in one API call |
| 🔒 **PII Redaction** | Emails, phones, credit cards (Luhn-checked), SSNs, IPs masked before LLM |
| 🔄 **Agentic Fallback** | Low confidence → auto-escalate to stronger model |
| 💰 **Cost Tracking** | Per-call USD breakdown with aggregate totals |
| 🛡️ **Prompt Injection Guard** | Delimiter-based isolation + instruction hierarchy |
| 📌 **Prompt Versioning** | Every result stamped with `prompt_version` for traceability |
| 🎨 **Premium Web UI** | Dark glassmorphism theme with real-time confidence visualization |
| ⚡ **Retry with Backoff** | Exponential backoff for rate limits and transient errors |

## 🏗️ Architecture

```
                     +----------------------+
   raw ticket -----> |   PII redaction      |  emails, phones, cards, SSNs
                     +----------+-----------+
                                |
                                v
                     +----------------------+
                     |   Versioned prompt   |  v1.0.0; ticket wrapped in
                     +----------+-----------+  <ticket>...</ticket>
                                |
                                v
                     +----------------------+
                     |  OpenAI-compatible   |  primary: gpt-4o-mini
                     |  API (tool-use)      |  temperature=0
                     +----------+-----------+
                                |
                                v
                     +----------------------+
                     |   Pydantic validate  |  enums, ranges, length caps
                     |   + business rules   |  category→team consistency
                     +----------+-----------+
                                |
                   low conf / failure
                                |
                                v  (escalate once)
                     +----------------------+
                     | claude-3.5-sonnet    |
                     +----------+-----------+
                                |
                                v
                  TicketClassification (JSON)
```

## 📁 Project Structure

```
support-ticket-classifier/
├── classifier/
│   ├── __init__.py          # Package exports
│   ├── classifier.py        # Core classification engine + retry logic
│   ├── cost.py              # Per-call USD cost tracking
│   ├── pii.py               # PII detection & redaction
│   ├── prompts.py           # Versioned prompt templates
│   └── schema.py            # Pydantic models + enum definitions
├── demo_ui/
│   ├── index.html           # Premium glassmorphism Web UI
│   ├── styles.css           # Dark theme styling
│   └── app.js               # Frontend logic
├── data/
│   └── sample_tickets.json  # Test ticket dataset
├── tests/                   # Unit tests (no API calls)
├── config.py                # Environment & model configuration
├── server.py                # Flask API server
├── main.py                  # CLI entry point
├── requirements.txt         # Python dependencies
├── start.sh                 # Render deployment script
└── .env.example             # Environment template
```

## 🔧 Skills Covered

| Skill | Where it lives |
| --- | --- |
| Schema Design | `classifier/schema.py` — Pydantic + enums |
| Structured Output from LLM | `classifier/classifier.py` — OpenAI tool-use |
| Validate LLM Response | `classifier/classifier.py` — Pydantic + business rules |
| Control LLM Non-Determinism | `temperature=0`, enum-constrained schema, deterministic prompt |
| Prompt Injection Defense | `classifier/prompts.py` — `<ticket>` delimiter, instruction hierarchy |
| Prompt Versioning | `classifier/prompts.py` — every result stamps `prompt_version` |
| Cost Calculation | `classifier/cost.py` — per-call USD + aggregate `CostTracker` |
| PII Detection / Redaction | `classifier/pii.py` — emails, phones, cards (Luhn), SSNs, IPs |
| Fallback / Retry | `classifier/classifier.py` — exp. backoff + model escalation |

## 🚀 Quick Start

### Local Setup

```bash
# Clone the repository
git clone https://github.com/mugeshkumards/Support-Ticket-Classifier.git
cd Support-Ticket-Classifier

# Install dependencies
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

### CLI Usage

```bash
# Classify bundled sample tickets
python main.py

# Classify your own tickets
python main.py path/to/your_tickets.json

# Pipe output to file
python main.py > classifications.json
```

### Web UI

```bash
python server.py
# Open http://localhost:5000
```

## 🧪 Run Tests

```bash
python -m pytest tests/
```

Tests cover PII redaction, schema validation, and cost calculation — no API calls needed.

## 📊 Example Output

```json
{
  "ticket_id": "TKT-1001",
  "category": "billing",
  "team": "billing_team",
  "priority": "high",
  "sentiment": "frustrated",
  "confidence": 0.93,
  "summary": "Customer was charged twice for order #88421 and is requesting a refund of the duplicate charge.",
  "reasoning": "Two charges on the same card for one order is a billing/payment issue, blocks the customer's refund, and customer tone is frustrated. Routes to billing_team.",
  "model_used": "openai/gpt-4o-mini",
  "prompt_version": "v1.0.0",
  "classified_at": "2026-04-28T12:34:56.789012"
}
```

## 💡 Model Strategy

| Model | Role | Input (per 1M) | Output (per 1M) |
| --- | --- | --- | --- |
| `gpt-4o-mini` | Primary — fast & cheap | $0.15 | $0.60 |
| `claude-3.5-sonnet` | Fallback — high accuracy | $3.00 | $15.00 |

The dual-model approach keeps average cost near GPT-4o Mini pricing while preserving accuracy on edge-case tickets through agentic escalation.

## 🌐 Deployment

Deployed on **Render** using Gunicorn:

```bash
# start.sh
gunicorn server:app
```

**Live Demo:** [https://support-ticket-classifier-jtu5.onrender.com](https://support-ticket-classifier-jtu5.onrender.com)

> **Note:** The Render free tier may take ~30 seconds to cold-start. Please be patient on the first load.

---

## 👤 Author

**Mugesh Kumar D S**
- GitHub: [@mugeshkumards](https://github.com/mugeshkumards)

---

<p align="center">
  <b>⭐ If you found this project helpful, give it a star!</b>
</p>

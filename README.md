# AI-Powered Support Ticket Classifier

> Project 01 — LLM Engineering
>
> An e-commerce company receives customer issues from two channels (web forms
> and emails). This service classifies each ticket and returns a JSON object
> that downstream services (routing, SLA, analytics) can consume.

For each ticket the classifier returns:

- **Category** — billing, shipping, product defect, returns, login, etc.
- **Team** — which team should own it (billing, logistics, engineering, …)
- **Priority** — low / medium / high / urgent
- **Sentiment** — positive / neutral / negative / frustrated
- **Confidence** — the model's honest self-assessment (0.0 – 1.0)
- A short `summary` and `reasoning` for human reviewers

## Skills covered

| Skill | Where it lives |
| --- | --- |
| Schema Design | `classifier/schema.py` — Pydantic + enums |
| Structured Output from LLM | `classifier/classifier.py` — Anthropic tool-use |
| Validate LLM Response | `classifier/classifier.py` — Pydantic + business rules |
| Control LLM's Non-Determinism | `temperature=0`, enum-constrained schema, deterministic prompt |
| Prompt Injection | `classifier/prompts.py` — `<ticket>` delimiter, instruction hierarchy |
| Prompt Versioning | `classifier/prompts.py` — every result stamps `prompt_version` |
| Cost Calculation | `classifier/cost.py` — per-call USD + aggregate `CostTracker` |
| PII Detection / Redaction | `classifier/pii.py` — emails, phones, cards (Luhn-checked), SSNs, IPs |
| Fallback / Retry | `classifier/classifier.py` — exp. backoff + Haiku → Sonnet escalation |

## Architecture

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
                     | Anthropic Messages   |  primary: claude-haiku-4-5
                     | API (tool-use forced)|  temperature=0
                     +----------+-----------+
                                |
                                v
                     +----------------------+
                     |   Pydantic validate  |  enums, ranges, length caps
                     |   + business rules   |  category->team consistency
                     +----------+-----------+
                                |
                  low conf / failure
                                |
                                v  (escalate once)
                     +----------------------+
                     |  claude-sonnet-4-6   |
                     +----------+-----------+
                                |
                                v
                  TicketClassification (JSON)
```

## Setup

```bash
cd "support-ticket-classifier"
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

## Run

Classify the bundled sample tickets:

```bash
python main.py
```

Classify your own file (same JSON shape as `data/sample_tickets.json`):

```bash
python main.py path/to/your_tickets.json
```

The classified results are printed to **stdout** as a JSON array. Progress and
the cost summary go to **stderr**, so you can pipe stdout to a file:

```bash
python main.py > classifications.json
```

## Run the offline tests

The unit tests do not call the API — they cover redaction, schema validation,
and cost calculation:

```bash
python -m pytest tests/
```

## Example output

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
  "model_used": "claude-haiku-4-5",
  "prompt_version": "v1.0.0",
  "classified_at": "2026-04-28T12:34:56.789012"
}
```

## Notes on model choice

- **Primary: `claude-haiku-4-5`** — fast and cheap ($1 / $5 per MTok), and
  classification with a tightly-bounded schema is exactly the kind of task
  Haiku is built for.
- **Fallback: `claude-sonnet-4-6`** — used only when Haiku returns low
  confidence or fails validation. This keeps the average per-ticket cost
  near Haiku pricing while preserving accuracy on the hard tickets.

Pricing snapshot (per 1M tokens):

| Model | Input | Output |
| --- | --- | --- |
| claude-haiku-4-5 | $1.00 | $5.00 |
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-opus-4-7 | $5.00 | $25.00 |

## Web UI

A premium, glassmorphism-inspired dark theme UI is also available to interactively test the classifier. It uses a lightweight Flask backend.

```bash
pip install flask flask-cors
python server.py
```

Then open `http://localhost:5000` in your browser. The UI includes:
- **Sample Chips** to quickly test edge cases (like Prompt Injection, Double Billing, etc).
- **Real-time Confidence Bars** and badge-styled category displays.
- **Smart Alerts** for low confidence (flagged for review), prompt injection blocking, and model fallback escalation.

"""Flask API server for the Support Ticket Classifier UI.

Run:  python server.py
Then open http://localhost:5000 in your browser.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from classifier import SupportTicket, TicketClassifier

app = Flask(__name__, static_folder="demo_ui", static_url_path="")
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Lazy-init so the server starts even without a key (UI still loads).
_classifier: TicketClassifier | None = None


def _get_classifier() -> TicketClassifier:
    global _classifier
    if _classifier is None:
        _classifier = TicketClassifier()
    return _classifier


@app.route("/")
def index():
    return send_from_directory("demo_ui", "index.html")


@app.route("/api/classify", methods=["POST"])
def classify():
    data = request.get_json(force=True)
    ticket_id = data.get("ticket_id", "UI-0001")
    channel = data.get("channel", "web_form")
    subject = data.get("subject", "Support request")
    body = data.get("body", "")

    if not body.strip():
        return jsonify({"error": "Ticket body is required."}), 400

    ticket = SupportTicket(
        ticket_id=ticket_id,
        channel=channel,
        subject=subject,
        body=body,
    )

    try:
        clf = _get_classifier()
        result = clf.classify(ticket)
        payload = result.model_dump(mode="json")
        payload["cost"] = {
            "total_usd": clf.cost_tracker.total_usd,
            "calls": len(clf.cost_tracker.calls),
        }
        return jsonify(payload)
    except Exception as e:
        logger.exception("Classification failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/sample-tickets")
def sample_tickets():
    path = Path(__file__).parent / "data" / "sample_tickets.json"
    tickets = json.loads(path.read_text(encoding="utf-8"))
    return jsonify(tickets)


if __name__ == "__main__":
    app.run(debug=True, port=5000)

"""Demo entry point.

Usage:
    python main.py                  # classify all sample tickets
    python main.py data/foo.json    # classify a custom file

Each ticket in the input file produces a JSON classification object. At the
end the cost summary for the run is printed to stderr.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from classifier import SupportTicket, TicketClassifier


def _load_tickets(path: Path) -> list[SupportTicket]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [SupportTicket(**item) for item in raw]


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).parent / "data" / "sample_tickets.json"

    tickets = _load_tickets(input_path)
    classifier = TicketClassifier()

    results = []
    for ticket in tickets:
        print(f"\n--- Classifying {ticket.ticket_id} ---", file=sys.stderr)
        try:
            result = classifier.classify(ticket)
        except Exception as e:                # noqa: BLE001
            print(f"FAILED: {ticket.ticket_id}: {e}", file=sys.stderr)
            continue
        results.append(result.model_dump(mode="json"))
        print(
            f"  -> {result.category.value} / {result.team.value} / "
            f"{result.priority.value} / conf={result.confidence:.2f} "
            f"[{result.model_used}]",
            file=sys.stderr,
        )

    print(json.dumps(results, indent=2, default=str))

    print(f"\n{classifier.cost_tracker.summary()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

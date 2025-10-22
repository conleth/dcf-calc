from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, request, send_from_directory

from backend.valuation_service import ValuationService

BASE_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    static_folder=str(BASE_DIR / "frontend"),
    static_url_path="",
)
service = ValuationService()


@app.route("/")
def index() -> Any:
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/valuation", methods=["POST"])
def valuate() -> Any:
    try:
        payload: Dict[str, Any] = request.get_json(force=True, silent=False) or {}
        result = service.valuate(payload)
        return jsonify(result)
    except Exception as exc:  # broad catch to surface manageable errors to UI
        return jsonify({"error": str(exc)}), 400


@app.route("/api/batch", methods=["POST"])
def batch() -> Any:
    try:
        payload = request.get_json(force=True, silent=False) or {}
        tickers = payload.get("tickers") or []
        tickers = [str(t).strip().upper() for t in tickers if str(t).strip()]
        if not tickers:
            raise ValueError("Provide a list of tickers to evaluate.")
        shared_inputs = {k: v for k, v in payload.items() if k not in {"tickers"}}
        valuations = []
        for ticker in tickers:
            inputs = {**shared_inputs, "ticker": ticker}
            valuations.append({"ticker": ticker, "result": service.valuate(inputs)})
        return jsonify({"results": valuations})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/health", methods=["GET"])
def health() -> Any:
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(app.config.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

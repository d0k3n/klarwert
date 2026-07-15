import sys
import json
import logging
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from portfolio.parser import parse_csv
from portfolio.engine import run_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).parent / "transactions.csv"
KD_PATH = Path(__file__).parent / "knocked_down.json"

if not CSV_PATH.exists():
    logger.error("transactions.csv not found at %s", CSV_PATH)
    sys.exit(1)

df = parse_csv(str(CSV_PATH))
logger.info("Loaded %d transactions from %s", len(df), CSV_PATH)


def load_knocked_ids():
    if KD_PATH.exists():
        return set(json.loads(KD_PATH.read_text(encoding="utf-8")).get("ids", []))
    return set()


def compute_data(flagged_ids=None):
    d = df.copy()
    if flagged_ids:
        d["knocked"] = (d["tx_type"] == "BUY") & (d["transaction_id"].isin(flagged_ids))
    return run_engine(d)


app = Flask(__name__)


@app.route("/api/reload", methods=["POST"])
def api_reload():
    global df
    try:
        df = parse_csv(str(CSV_PATH))
        logger.info("Reloaded %d transactions from %s", len(df), CSV_PATH)
        return jsonify({"ok": True, "count": len(df)})
    except Exception as e:
        logger.error("Reload failed: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/api/summary")
def api_summary():
    return jsonify(compute_data(load_knocked_ids())["summary"])


@app.route("/api/open_positions")
def api_open_positions():
    return jsonify(compute_data(load_knocked_ids())["open_positions"])


@app.route("/api/closed_positions")
def api_closed_positions():
    return jsonify(compute_data(load_knocked_ids())["closed_positions"])


@app.route("/api/cash_flow")
def api_cash_flow():
    return jsonify(compute_data(load_knocked_ids())["cash_flow"])


@app.route("/api/transactions")
def api_transactions():
    return jsonify(compute_data(load_knocked_ids())["transactions"])


@app.route("/api/products")
def api_products():
    return jsonify(compute_data(load_knocked_ids())["products"])


@app.route("/api/monthly_pl")
def api_monthly_pl():
    return jsonify(compute_data(load_knocked_ids())["monthly_pl"])


@app.route("/api/knocked_down")
def api_knocked_down():
    return jsonify({"ids": sorted(load_knocked_ids())})


@app.route("/api/knocked_down/toggle", methods=["POST"])
def api_knocked_down_toggle():
    body = request.get_json()
    txn_id = body.get("id", "")
    if not txn_id:
        return jsonify({"ok": False, "error": "missing id"}), 400
    ids = load_knocked_ids()
    if txn_id in ids:
        ids.remove(txn_id)
    else:
        ids.add(txn_id)
    KD_PATH.write_text(json.dumps({"ids": sorted(ids)}), encoding="utf-8")
    return jsonify({"ok": True, "flagged": txn_id in ids})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

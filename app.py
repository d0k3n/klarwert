import sys
import os
import json
import io
import logging
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from portfolio.parser import parse_csv
from portfolio.engine import run_engine, compute_derivative_executions, compute_card_transactions, auto_detect_knocked
from portfolio.tax_report import build_tax_report
import support

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", None) or str(Path(__file__).parent)
    return str(Path(base) / rel)


if getattr(sys, "_MEIPASS", None):
    BASE_DIR = Path(os.environ.get("APPDATA", Path.home())) / "Klarwert"
    BASE_DIR.mkdir(parents=True, exist_ok=True)
else:
    BASE_DIR = Path(__file__).parent

CSV_PATH = BASE_DIR / "transactions.csv"
KD_PATH = BASE_DIR / "knocked_down.json"
PRICES_PATH = BASE_DIR / "prices.json"


def load_prices():
    if PRICES_PATH.exists():
        return {k: float(v) for k, v in json.loads(PRICES_PATH.read_text(encoding="utf-8")).items()}
    return {}


def save_prices(prices):
    PRICES_PATH.write_text(json.dumps(prices, indent=2), encoding="utf-8")

df = None
if CSV_PATH.exists():
    try:
        df = parse_csv(str(CSV_PATH))
        logger.info("Loaded %d transactions from %s", len(df), CSV_PATH)
    except Exception as e:
        logger.error("Failed to load %s: %s", CSV_PATH, e)
else:
    logger.warning("No transactions.csv found; waiting for CSV upload.")


def load_knocked_ids():
    if KD_PATH.exists():
        return set(json.loads(KD_PATH.read_text(encoding="utf-8")).get("ids", []))
    return set()


def compute_data(flagged_ids=None):
    if df is None:
        return EMPTY_RESULT
    ids = frozenset(flagged_ids or ())
    if _cache["result"] is not None and _cache["ids"] == ids:
        return _cache["result"]
    d = df.copy()
    flagged = set(flagged_ids or ())
    auto = auto_detect_knocked(d)
    merged = flagged | auto
    if merged:
        d["knocked"] = (d["tx_type"] == "BUY") & (d["transaction_id"].isin(merged))
    result = run_engine(d)
    _cache["ids"] = ids
    _cache["result"] = result
    return result


EMPTY_RESULT = {
    "summary": {},
    "open_positions": [],
    "closed_positions": [],
    "cash_flow": [],
    "transactions": [],
    "products": [],
    "monthly_pl": [],
    "lot_matches": [],
}


_cache = {"ids": None, "result": None}


def invalidate_cache():
    _cache["ids"] = None
    _cache["result"] = None


app = Flask(__name__, template_folder=resource_path("templates"), static_folder=resource_path("static"))


@app.route("/api/reload", methods=["POST"])
def api_reload():
    global df
    if not CSV_PATH.exists():
        return jsonify({"ok": False, "error": "no CSV loaded"}), 400
    try:
        df = parse_csv(str(CSV_PATH))
        invalidate_cache()
        logger.info("Reloaded %d transactions from %s", len(df), CSV_PATH)
        return jsonify({"ok": True, "count": len(df)})
    except Exception as e:
        logger.error("Reload failed: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/upload", methods=["POST"])
def api_upload():
    global df
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "no file provided"}), 400
    try:
        raw = f.read()
        parsed = parse_csv(io.BytesIO(raw))
    except Exception as e:
        logger.error("Upload parse failed: %s", e)
        return jsonify({"ok": False, "error": f"invalid CSV: {e}"}), 400
    try:
        CSV_PATH.write_bytes(raw)
    except Exception as e:
        logger.warning("Could not persist CSV to %s: %s", CSV_PATH, e)
    df = parsed
    invalidate_cache()
    logger.info("Loaded %d transactions from upload %s", len(df), f.filename)
    return jsonify({"ok": True, "count": len(df), "filename": f.filename})


@app.route("/api/status")
def api_status():
    return jsonify({"loaded": df is not None, "count": len(df) if df is not None else 0})


@app.route("/api/support")
def api_support():
    return jsonify({
        "donation_url": support.DONATION_URL,
        "github_url": support.GITHUB_URL,
    })


@app.route("/")
def index():
    return send_from_directory(resource_path("templates"), "index.html")


@app.route("/api/summary")
def api_summary():
    return jsonify(compute_data(load_knocked_ids())["summary"])


@app.route("/api/open_positions")
def api_open_positions():
    return jsonify(compute_data(load_knocked_ids())["open_positions"])


@app.route("/api/prices", methods=["GET"])
def api_prices_get():
    return jsonify(load_prices())


@app.route("/api/prices", methods=["POST"])
def api_prices_post():
    body = request.get_json(silent=True) or {}
    isin = (body.get("isin") or "").strip()
    if not isin:
        return jsonify({"ok": False, "error": "missing isin"}), 400
    prices = load_prices()
    price = body.get("price")
    if price is None:
        prices.pop(isin, None)
    else:
        try:
            prices[isin] = float(price)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "invalid price"}), 400
    save_prices(prices)
    return jsonify({"ok": True, "prices": prices})


@app.route("/api/valued_positions")
def api_valued_positions():
    result = compute_data(load_knocked_ids())
    return jsonify(apply_prices(result["open_positions"], load_prices()))


@app.route("/api/closed_positions")
def api_closed_positions():
    return jsonify(compute_data(load_knocked_ids())["closed_positions"])


@app.route("/api/performance")
def api_performance():
    if df is None:
        return jsonify({})
    return jsonify(compute_performance(df, compute_data(load_knocked_ids())))


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


@app.route("/api/lot_matches")
def api_lot_matches():
    return jsonify(compute_data(load_knocked_ids())["lot_matches"])


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
    invalidate_cache()
    return jsonify({"ok": True, "flagged": txn_id in ids})


@app.route("/api/tax_report")
def api_tax_report():
    if df is None:
        return jsonify({"year": None, "disposals": [], "disposal_totals": {},
                        "dividends": [], "dividend_totals": {}, "interest": 0.0, "saveback": 0.0})
    year = request.args.get("year", type=int)
    if not year:
        year = int(df["datetime"].max().year)
    result = compute_data(load_knocked_ids())
    return jsonify(build_tax_report(df, result["lot_matches"], year))


@app.route("/api/card_transactions")
def api_card_transactions():
    if df is None:
        return jsonify([])
    return jsonify(compute_card_transactions(df))


@app.route("/api/derivative_executions")
def api_derivative_executions():
    if df is None:
        return jsonify([])
    manual = load_knocked_ids()
    auto = auto_detect_knocked(df)
    merged = manual | auto
    return jsonify(compute_derivative_executions(df, merged))


@app.route("/api/income")
def api_income():
    if df is None:
        return jsonify({"monthly": [], "dividends": []})
    return jsonify(compute_income(df))


@app.route("/api/spending")
def api_spending():
    if df is None:
        return jsonify({"by_category": [], "monthly": []})
    return jsonify(compute_spending(df))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

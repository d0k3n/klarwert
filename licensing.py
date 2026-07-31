import os
import sys
import json
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

LS_API = "https://api.lemonsqueezy.com/v1/licenses"
PRODUCT_ID = int(os.environ.get("LS_PRODUCT_ID", "0"))

DEV_LICENSE = os.environ.get("TR_DEV_LICENSE") == "1"
if DEV_LICENSE:
    logger.warning("DEV LICENSE MODE active - license check bypassed")


def _app_data_dir():
    if getattr(sys, "_MEIPASS", None):
        d = Path(os.environ.get("APPDATA", Path.home())) / "TradeRepublicAnalyzer"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


LICENSE_PATH = _app_data_dir() / "license.json"


def _load():
    if LICENSE_PATH.exists():
        try:
            return json.loads(LICENSE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save(data):
    LICENSE_PATH.write_text(json.dumps(data), encoding="utf-8")


def _clear():
    if LICENSE_PATH.exists():
        LICENSE_PATH.unlink()


def activate(key):
    if DEV_LICENSE:
        _save({"license_key": key, "instance_id": "dev"})
        return {"ok": True, "dev": True}
    if not PRODUCT_ID:
        return {"ok": False, "error": "product not configured"}
    try:
        r = requests.post(
            f"{LS_API}/activate",
            json={
                "license_key": key,
                "instance_name": "TradeRepublicAnalyzer",
                "product_id": PRODUCT_ID,
            },
            timeout=20,
        )
        data = r.json()
    except requests.RequestException as e:
        return {"ok": False, "error": f"network error: {e}"}
    if data.get("activated"):
        instance = data.get("instance") or {}
        _save({"license_key": key, "instance_id": instance.get("id")})
        return {"ok": True}
    return {"ok": False, "error": (data.get("error") or "invalid license key")}


def is_activated():
    if DEV_LICENSE:
        return True
    lic = _load()
    if not lic:
        return False
    try:
        r = requests.post(
            f"{LS_API}/validate",
            json={
                "license_key": lic["license_key"],
                "instance_id": lic["instance_id"],
            },
            timeout=20,
        )
        data = r.json()
    except requests.RequestException:
        return True
    if data.get("valid"):
        return True
    _clear()
    return False


def deactivate():
    lic = _load()
    if not lic:
        return
    try:
        requests.post(
            f"{LS_API}/deactivate",
            json={
                "license_key": lic["license_key"],
                "instance_id": lic["instance_id"],
            },
            timeout=20,
        )
    except requests.RequestException:
        pass
    _clear()

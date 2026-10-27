"""余额查询：复用 session.json 里的请求模板，每次刷新时间戳并重算签名。"""

import json
import os
import random
import time

import requests

from . import crypto as sc
from .config import APP_DIR

DROP_HEADERS = {"content-length", "host", "accept-encoding", "connection"}
THROTTLE = APP_DIR / ".http_last"
MIN_INTERVAL = 5  # 秒；服务端对同一户号的短间隔重复查询会返回 101009/101014


class TokenExpired(RuntimeError):
    pass


def _throttle():
    try:
        if THROTTLE.exists():
            wait = MIN_INTERVAL - (time.time() - float(THROTTLE.read_text().strip()))
            if wait > 0:
                time.sleep(wait)
    except (OSError, ValueError):
        pass
    try:
        THROTTLE.write_text(str(time.time()))
    except OSError:
        pass


def _now_headers():
    ms = str(int(time.time() * 1000))
    stamp = time.strftime("%Y%m%d%H%M%S") + f"{random.randint(0, 999999999):09d}"
    return ms, stamp


def _post(session: dict) -> dict:
    body = {"data": session["data"], "skey": session["skey"]}
    ms, stamp = _now_headers()
    body["timestamp"] = ms
    body["sign"] = sc.sign_envelope(session["skey"], session["data"], ms)

    headers = {k: v for k, v in session["headers"].items() if k.lower() not in DROP_HEADERS}
    headers["y"] = ms
    headers["timestamp"] = stamp

    resp = requests.post(
        session["url"],
        data=json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(),
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def query(session: dict) -> dict:
    last = None
    for attempt, backoff in enumerate((0, 8, 16)):
        if backoff:
            time.sleep(backoff)
        _throttle()
        payload = _post(session)
        if "encryptData" in payload:
            return sc.open_response(payload)
        last = payload
        if payload.get("code") not in (101009, 101014):
            break
    raise RuntimeError(f"服务端未返回密文: {last.get('code')} {last.get('message')}")


def extract_account(plain: dict) -> dict:
    arr = plain["data"]["data"]["ELEC_TYPE_LIST"][0]["ARREARS_LIST"][0]
    return {
        "balance": int(arr["BALANCE"]) / 100 if arr.get("BALANCE") not in (None, "") else None,
        "available": (
            int(arr["AVALIABLE_BALANCE"]) / 100
            if arr.get("AVALIABLE_BALANCE") not in (None, "")
            else None
        ),
        "account_no": arr.get("POWER_USER_ID") or arr.get("SENSITIVE_POWER_USER_ID"),
        "address": arr.get("POWER_USER_ADDR"),
        "as_of": arr.get("DEADLINE_TIME"),
    }


def fetch(session: dict) -> dict:
    return extract_account(query(session))


def load_session(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

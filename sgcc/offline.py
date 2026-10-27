"""脱机登录：短信验证码流程，不依赖手机 / ADB / 抓包。

接口（emss-uia-center-front）：
  c1/f01  发送短信验证码 -> codeKey
  c2/f02  提交 codeKey + 验证码 -> token
"""

import base64
import hashlib
import json
import time

import requests

from . import api, crypto as sc
from .config import credentials, save_json

BASE = "https://csc-service.sgcc.com.cn:28002/"
SMS_PATH = "emss-uia-center-front/member/c1/f01"
CODE_PATH = "emss-uia-center-front/member/c2/f02"
PUSH_ID = "000000"


def usc_info():
    return {
        "isEncrypt": False,
        "devciceIp": "127.0.0.1",
        "devciceId": "000000",
        "tenant": "state_grid",
        "member": "2202",
    }


def _param_md5(obj):
    s = ""
    for k in sorted(obj):
        s += k + json.dumps(obj[k], ensure_ascii=False, separators=(",", ":"))
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _post(session, path, payload):
    sealed = sc.seal_request(payload)
    ms, stamp = api._now_headers()
    body = dict(sealed)
    body["timestamp"] = ms
    body["sign"] = sc.sign_envelope(body["skey"], body["data"], ms)

    headers = {k: v for k, v in session["headers"].items() if k.lower() not in api.DROP_HEADERS}
    headers["y"] = ms
    headers["timestamp"] = stamp
    headers["md5"] = _param_md5(payload)
    headers["timeStamp"] = time.strftime("%Y%m%d%H%M%S")

    api._throttle()
    resp = requests.post(
        BASE + path,
        data=json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(),
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return sc.open_response(data) if "encryptData" in data else data


def request_code(session, account=None):
    phone = account or credentials()[0]
    if not phone:
        raise RuntimeError('缺少手机号：写入 ~/.sgcc/config.json {"phone": "..."}')
    payload = {
        "uscInfo": usc_info(),
        "quInfo": {"sendType": "0", "account": phone, "businessType": "login"},
    }
    plain = _post(session, SMS_PATH, payload)
    data = plain.get("data") or {}
    bizrt = data.get("bizrt") or {}
    key = bizrt.get("codeKey")
    if not key:
        srvrt = data.get("srvrt") or {}
        msg = srvrt.get("resultMessage") or plain.get("message") or plain
        raise RuntimeError(f"发送验证码失败：{msg}")
    return key, phone


def submit_code(session, code_key, code, account):
    payload = {
        "uscInfo": usc_info(),
        "quInfo": {
            "account": account,
            "codeKey": code_key,
            "code": code,
            "pushId": PUSH_ID,
            "businessType": "login",
            "optSys": "android",
        },
    }
    plain = _post(session, CODE_PATH, payload)
    data = plain.get("data") or {}
    bizrt = data.get("bizrt") or {}
    if not bizrt.get("token"):
        srvrt = data.get("srvrt") or {}
        msg = bizrt.get("errors") or srvrt.get("resultMessage") or plain.get("message") or plain
        raise RuntimeError(f"登录失败：{msg}")
    return bizrt


def _user_id(bizrt):
    info = bizrt.get("userInfo")
    if isinstance(info, dict):
        for k in ("userId", "userid", "USER_ID", "id"):
            if info.get(k):
                return str(info[k])
    return ""


def login(session_path, code=None, account=None, prompt=input):
    session = api.load_session(session_path)
    code_key, phone = request_code(session, account)
    if code is None:
        code = prompt("短信验证码：").strip()
    bizrt = submit_code(session, code_key, code, phone)
    apply_token(session, bizrt)
    save_json(session_path, session)
    return session["headers"]["t"]


def apply_token(session, bizrt):
    token = bizrt["token"]
    session["headers"]["t"] = token
    uid = _user_id(bizrt) or session["headers"].get("userid", "")
    if uid:
        session["headers"]["userid"] = uid
        b64 = base64.b64encode(f"{uid}_{token}".encode()).decode()
        session["headers"]["x-tingyun"] = "c=A|ehS_ryOQceY;u=base64#" + b64 + ";"
    expire = bizrt.get("expirationDate")
    if expire and len(str(expire)) == 12:
        e = str(expire)
        session["expires_at"] = (
            f"{e[0:4]}-{e[4:6]}-{e[6:8]} {e[8:10]}:{e[10:12]}"
        )
    elif bizrt.get("tokenExpireTime"):
        # 时长（秒），不是时间戳
        session["expires_at"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(time.time() + int(bizrt["tokenExpireTime"]))
        )
    session["captured_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return token

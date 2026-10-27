"""登录并刷新 session.json 里的凭证。

设备已被信任时一般不需要短信验证码；若服务端要求，会提示输入（或用 --code）。
"""

import base64
import os
import re
import sys
import tempfile
import time

from . import device, safekb
from .config import credentials, save_json

PKG = device.PKG
SPLASH = device.SPLASH
DB = "/data/data/com.sgcc.wsgw.cn/databases/com.sgcc.wsgw.cn_nbsdatacache.db"
KEEPER_IN = "/data/local/tmp/.c"

DISMISS = (
    "同意并继续", "同意", "允许", "始终允许", "仅在使用中允许",
    "暂不开启", "我知道了", "以后再说", "跳过", "不再提示", "关闭",
)

TOKEN_RE = re.compile(r"99t[a-z0-9]{20,40}")


def log(msg):
    print(msg, flush=True)


def ui_nodes():
    return device.nodes()


def find(ns, pred):
    return device.find(ns, pred)


def find_text(ns, text, contains=False):
    return device.find_text(ns, text, contains)


def find_rid(ns, suffix):
    return find(ns, lambda n: (n["rid"] or "").endswith(suffix))


def ui_tap(n):
    device.tap(n["x"], n["y"])


def dismiss_common(ns):
    for label in DISMISS:
        n = find_text(ns, label)
        if n:
            ui_tap(n)
            time.sleep(1.0)
            return True
    return False


def ensure_home(timeout=60):
    device.shell(f"am start -n {SPLASH}")
    end = time.time() + timeout
    while time.time() < end:
        ns = ui_nodes()
        if dismiss_common(ns):
            continue
        if logged_in(ns):
            return "logged_in", ns
        if find_text(ns, "请先登录", contains=True) or find_text(ns, "欢迎使用网上国网"):
            return "logged_out", ns
        time.sleep(1.2)
    return None, []


def open_login(ns):
    n = find_text(ns, "请先登录", contains=True) or find_text(ns, "登录/注册", contains=True)
    ui_tap(n) if n else device.tap(284, 225)
    end = time.time() + 15
    while time.time() < end:
        ns = ui_nodes()
        if find_text(ns, "欢迎登录网上国网", contains=True) or find_text(ns, "立即登录"):
            return True, ns
        time.sleep(1.0)
    return False, ns


def fill_phone(ns, phone):
    n = find_rid(ns, "input_mobile_number_et")
    if not n:
        return False, ns
    ui_tap(n)
    time.sleep(1.0)
    for _ in range(20):
        device.shell("input keyevent 67")
    device.shell(f"input text {phone}")
    time.sleep(0.8)
    device.shell("input keyevent 4")
    time.sleep(0.8)
    ns = ui_nodes()
    n = find_rid(ns, "input_mobile_number_et")
    digits = re.sub(r"\D", "", n["text"] if n else "")
    return digits == phone, ns


def agreement_checked(ns):
    n = find_rid(ns, "user_activity_agreement_tv")
    return bool(n and "已勾选" in n["desc"])


def set_agreement(ns, checked):
    if agreement_checked(ns) == checked:
        return True
    n = find_rid(ns, "user_activity_agreement_tv")
    if not n:
        return False
    ui_tap(n)
    time.sleep(0.7)
    return agreement_checked(ui_nodes()) == checked


def type_password(ns, password):
    n = find_rid(ns, "input_pwd_et")
    if not n:
        return False, "no password field"
    ui_tap(n)
    time.sleep(1.6)
    if not safekb.kb_open():
        ui_tap(n)
        time.sleep(1.6)
    if not safekb.kb_open():
        return False, "secure keyboard did not open"
    safekb.show_plaintext()
    safekb.clear()
    needed = set(password.lower())
    keys = safekb.find_keys(needed=needed)
    missing = needed - set(keys)
    if missing:
        return False, f"missing keys {sorted(missing)}"
    got = safekb.type_text(password, keys)
    if got != password:
        safekb.clear()
        got = safekb.type_text(password, keys)
    if got != password:
        return False, f"typed {got!r}"
    device.shell("input keyevent 4")
    time.sleep(1.2)
    if safekb.read_pwd() != password:
        return False, f"lost after close ({safekb.read_pwd()!r})"
    return True, ""


def logged_in(ns):
    """登录后首页把「去交费」放在 content-desc 上，不是 text。"""
    return any(
        "去交费" in (n["text"] or "") or (n["desc"] or "").strip() == "去交费" for n in ns
    )


def captcha_open(ns):
    """验证码弹窗（content-desc 为「验证码」）。"""
    return any((n["desc"] or "").strip() == "验证码" for n in ns)


def solve_captcha(ns, timeout=90):
    """切换到无障碍验证方式，等待其自动通过。"""
    n = find(ns, lambda x: "换一种验证方式" in (x["desc"] or ""))
    if n:
        ui_tap(n)
        time.sleep(2)
    end = time.time() + timeout
    while time.time() < end:
        if not captcha_open(ui_nodes()):
            return True
        time.sleep(1.5)
    return False


def settle_login(code=None, timeout=45):
    """等待提交结果：'ok' 登录成功，'captcha' 需要过验证码，'fail' 超时。"""
    end = time.time() + timeout
    while time.time() < end:
        ns = ui_nodes()
        if logged_in(ns):
            return "ok"
        if captcha_open(ns):
            return "captcha"
        if find_text(ns, "暂不开启") or find_text(ns, "请开启指纹登录", contains=True):
            n = find_text(ns, "暂不开启")
            if n:
                ui_tap(n)
            time.sleep(2)
            continue
        if find_text(ns, "请输入验证码", contains=True) or find_text(ns, "获取验证码"):
            if code is None:
                code = input("需要短信验证码，请输入：").strip()
            f = find(ns, lambda x: x["cls"].endswith("EditText"))
            if f:
                ui_tap(f)
                time.sleep(1.0)
                device.shell(f"input text {code}")
                time.sleep(0.5)
            btn = find_text(ns, "确定") or find_text(ns, "登录") or find_text(ns, "提交")
            if btn:
                ui_tap(btn)
            time.sleep(3)
            continue
        if dismiss_common(ns):
            continue
        time.sleep(1.5)
    return "fail"


def _read_root(path, timeout=20):
    """等待设备侧写出文件并读取内容。"""
    end = time.time() + timeout
    while time.time() < end:
        out = device.adb("shell", f"cat {path} 2>/dev/null").stdout.strip()
        if out:
            return out
        time.sleep(1.0)
    return ""


def get_token(timeout=25):
    """从手机读取登录凭证。"""
    ts = str(int(time.time()))
    out_path = f"/data/local/tmp/.o{ts}"
    script = (
        f"grep -a -o -E '99t[a-z0-9]{{20,40}}' {DB} | sort -u > {out_path}\n"
        f"chmod 644 {out_path}\n"
    )
    tmp = os.path.join(tempfile.gettempdir(), f"sgcc_tok_{ts}.sh")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(script)
    device.adb("push", tmp, KEEPER_IN)
    os.unlink(tmp)

    out = _read_root(out_path, timeout)
    toks = TOKEN_RE.findall(out)
    if not toks:
        # 兼容旧 keeper：固定输出到 .o
        time.sleep(5)
        out = device.adb("exec-out", "cat /data/local/tmp/.o").stdout
        toks = TOKEN_RE.findall(out)
    return toks[-1] if toks else None


def update_session(session_path, token):
    import json

    with open(session_path, encoding="utf-8") as f:
        s = json.load(f)
    uid = s["headers"].get("userid", "")
    s["headers"]["t"] = token
    if uid:
        b64 = base64.b64encode((uid + "_" + token).encode()).decode()
        s["headers"]["x-tingyun"] = "c=A|ehS_ryOQceY;u=base64#" + b64 + ";"
    s["captured_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_json(session_path, s)
    return token


def do_login(force=False, code=None):
    """确保已登录并返回最新 token。失败抛 RuntimeError。"""
    phone, password = credentials()
    if not phone or not password:
        raise RuntimeError(
            "缺少账号密码：写入 ~/.sgcc/config.json {\"phone\":\"...\",\"password\":\"...\"} 或设 SGCC_PHONE / SGCC_PASSWORD"
        )

    if "mDreamingLockscreen=true" in device.shell("dumpsys window | grep mDreamingLockscreen"):
        device.shell("input keyevent 82")
        time.sleep(1)

    if force:
        log("clearing app data...")
        device.shell(f"pm clear {PKG}")
        time.sleep(2)

    state, ns = ensure_home()
    log(f"home: {state}")
    if state is None:
        raise RuntimeError("首页未就绪")

    if state == "logged_in":
        log("已登录，跳过登录流程")
        return get_token()

    ok, ns = open_login(ns)
    if not ok:
        raise RuntimeError("登录页未打开")
    log("login page ok")

    ok, ns = fill_phone(ns, phone)
    log("phone ok" if ok else "phone FAIL")
    if not ok:
        raise RuntimeError("手机号填写失败")

    # 扫描期间先取消勾选，避免误触键盘上的回车直接提交
    set_agreement(ns, False)
    ok, err = type_password(ns, password)
    log("password ok" if ok else f"password FAIL: {err}")
    if not ok:
        raise RuntimeError(f"密码输入失败: {err}")

    for attempt in range(1, 4):
        ns = ui_nodes()
        if not set_agreement(ns, True):
            raise RuntimeError("协议勾选失败")
        btn = find_text(ns, "立即登录")
        if not btn:
            raise RuntimeError("找不到登录按钮")
        ui_tap(btn)
        log(f"submitted ({attempt})...")

        status = settle_login(code)
        if status == "ok":
            log("logged in")
            break
        if status != "captcha":
            raise RuntimeError("登录未完成")

        log("captcha -> 无障碍验证")
        if not solve_captcha(ui_nodes()):
            raise RuntimeError("验证码未通过")
        log("captcha passed, resubmitting")
        # 通过后回到登录页且输入框被清空，需要重填
        ns = ui_nodes()
        if find_rid(ns, "input_mobile_number_et"):
            fill_phone(ns, phone)
            set_agreement(ns, False)
            ok, err = type_password(ui_nodes(), password)
            if not ok:
                raise RuntimeError(f"密码输入失败: {err}")
    else:
        raise RuntimeError("登录失败：重试次数用尽")

    token = get_token()
    if not token:
        raise RuntimeError("未能取到登录凭证")
    return token


def main():
    """调试入口：python -m sgcc.login --code 123456 --force"""
    import argparse

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="python -m sgcc.login")
    ap.add_argument("--code", help="短信验证码（若风控要求）")
    ap.add_argument("--force", action="store_true", help="清本地态后强制重新登录")
    args = ap.parse_args()

    from .config import session_path

    token = do_login(force=args.force, code=args.code)
    path = update_session(session_path(), token)
    print(f"token: {token}\nsession: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

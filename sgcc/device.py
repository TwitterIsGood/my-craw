"""ADB 设备交互：uiautomator 树解析 + UI 兜底余额读取。

仅 720x1280 / Android 6 的 OPPO A57 上实测过；其它机型坐标需自行调整。
"""

import os
import re
import subprocess
import time

ENV = dict(os.environ, MSYS_NO_PATHCONV="1")
PKG = "com.sgcc.wsgw.cn"
SPLASH = f"{PKG}/.SplashActivity"
LIST_ACTIVITY = "MultiElecListActivity"

NODE_RE = re.compile(r"<node\b[^>]*>")
ATTR_RE = r'{}\s*=\s*"([^"]*)"'


def adb(*args, timeout=45):
    return subprocess.run(
        ["adb", *args],
        env=ENV,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def shell(cmd, timeout=45):
    return adb("shell", cmd, timeout=timeout).stdout


def device_online():
    return bool(re.search(r"^\S+\s+device$", adb("devices").stdout, re.M))


def attr(tag, name):
    m = re.search(ATTR_RE.format(name), tag)
    return m.group(1) if m else ""


def nodes(path="/sdcard/sgcc_ui.xml"):
    shell(f"uiautomator dump --compressed {path} >/dev/null 2>&1")
    xml = adb("exec-out", f"cat {path}").stdout
    out = []
    for tag in NODE_RE.findall(xml):
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", attr(tag, "bounds"))
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        out.append(
            {
                "text": attr(tag, "text"),
                "desc": attr(tag, "content-desc"),
                "rid": attr(tag, "resource-id"),
                "cls": attr(tag, "class"),
                "x": (x1 + x2) // 2,
                "y": (y1 + y2) // 2,
                "x1": x1,
                "y1": y1,
                "y2": y2,
            }
        )
    return out


def find(ns, pred):
    return next((n for n in ns if pred(n)), None)


def find_text(ns, text, contains=False):
    if contains:
        return find(ns, lambda n: text in (n["text"] or ""))
    return find(ns, lambda n: (n["text"] or "").strip() == text)


def find_label(ns, label):
    """text 或 content-desc 任一命中；登录后首页把「去交费」放在 desc 上。"""
    return find(
        ns, lambda n: label in (n["text"] or "") or (n["desc"] or "").strip() == label
    )


def tap(x, y):
    shell(f"input tap {x} {y}")


def focus(node):
    tap(node["x"], node["y"])


def focused_activity():
    out = shell("dumpsys activity activities | grep -E 'mFocusedActivity|mResumedActivity'")
    m = re.search(r"u0 (" + re.escape(PKG) + r")/([^\s}]+)", out)
    return m.group(1) if m else ""


def wake_unlock():
    win = shell("dumpsys window | grep mDreamingLockscreen")
    if "mDreamingLockscreen=true" in win:
        shell("input keyevent 82")
        time.sleep(1)
    if "mShowingLockscreen=true" in shell("dumpsys window | grep mShowingLockscreen"):
        shell("input swipe 360 1150 360 400 250")
        time.sleep(1.5)


def wait_for(pred, timeout=40, interval=1.2):
    end = time.time() + timeout
    while time.time() < end:
        hit = pred(nodes())
        if hit:
            return hit
        time.sleep(interval)
    return None


def ensure_app():
    if find_label(nodes(), "去交费"):
        return True
    shell(f"am start -n {SPLASH}")
    time.sleep(6)
    return wait_for(
        lambda ns: find_label(ns, "去交费")
        or find_text(ns, "添加交费户号")
        or find_text(ns, "立即登录"),
        timeout=45,
    )


def goto_pay_page():
    if LIST_ACTIVITY in focused_activity():
        return True
    btn = find_label(nodes(), "去交费")
    if not btn:
        shell("input keyevent 3")
        ensure_app()
        btn = find_label(nodes(), "去交费")
    if not btn:
        return False
    tap(btn["x"], btn["y"])
    return bool(
        wait_for(lambda ns: find_text(ns, "添加交费户号") or find_text(ns, "去结算"), timeout=30)
    )


def expand_first_account():
    for _ in range(3):
        ns = nodes()
        if find_text(ns, "表内余额：", contains=True):
            return True
        row = find_text(ns, "用电户号：", contains=True)
        if not row:
            return False
        tap(300, max(row["y1"] - 45, 120))
        time.sleep(4)
        if find_text(nodes(), "表内余额：", contains=True):
            return True
    return False


def parse_account(ns):
    ref = find(ns, lambda n: "表内余额" in (n["text"] or ""))
    if not ref:
        return None
    cands = [
        n
        for n in ns
        if (n["text"] or "").strip()
        and abs(n["y"] - ref["y"]) <= 20
        and n["x1"] > ref["x1"]
        and re.fullmatch(r"[-+]?\d+(?:\.\d+)?", n["text"].strip())
    ]
    balance = cands[0]["text"].strip() if cands else None

    acct = find(ns, lambda n: (n["text"] or "").startswith("用电户号"))
    acct_no = None
    if acct:
        m = re.search(r"(\d{10,})", acct["text"])
        acct_no = m.group(1) if m else None
        if not acct_no:
            for n in ns:
                if abs(n["y"] - acct["y"]) <= 12 and n["x1"] > acct["x1"] + 50:
                    m = re.search(r"\d{10,}", n["text"] or "")
                    if m:
                        acct_no = m.group(0)
                        break
    addr = None
    for n in ns:
        t = (n["text"] or "").strip()
        if re.search(r"(市|区|县|路|街|村|栋|室)", t) and "截止" not in t and len(t) > 8:
            addr = t
            break
    ts = None
    for n in ns:
        m = re.search(r"截止时间[:：]\s*(.+)", n["text"] or "")
        if m:
            ts = m.group(1).strip(" )）")
            break
    info = {
        "balance": float(balance) if balance else None,
        "account_no": acct_no,
        "address": addr,
        "as_of": ts,
    }
    for label in ("补加金额", "扣减金额"):
        n = find(ns, lambda m, l=label: (m["text"] or "").startswith(l))
        if n:
            info[label] = next(
                (
                    x["text"]
                    for x in ns
                    if abs(x["y"] - n["y"]) <= 15 and x["x1"] > n["x1"] + 20
                ),
                None,
            )
    return info


def balance_ui():
    """ADB UI 兜底：返回账户 dict；失败抛 RuntimeError。"""
    wake_unlock()
    if not ensure_app():
        raise RuntimeError("首页未就绪")
    if find_text(nodes(), "立即登录"):
        raise RuntimeError("登录态失效，需要重新登录")
    if not goto_pay_page():
        raise RuntimeError("无法打开交费页")
    if not expand_first_account():
        raise RuntimeError("未找到户号卡片")
    info = parse_account(nodes())
    if not info or info.get("balance") is None:
        raise RuntimeError("未能解析余额")
    return info

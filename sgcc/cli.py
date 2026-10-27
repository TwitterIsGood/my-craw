"""命令行入口：sgcc {balance,refresh,login,doctor}。"""

import argparse
import json
import shutil
import sys

from . import __version__, api, config, device


def _emit(obj, as_json):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))


def _show_account(acct, as_json):
    if as_json:
        _emit(acct, True)
        return
    bal = acct.get("balance")
    print(f"余额      ¥{bal:.2f}" if bal is not None else "余额      未知")
    if acct.get("account_no"):
        print(f"户号      {acct['account_no']}")
    if acct.get("address"):
        print(f"地址      {acct['address']}")
    if acct.get("as_of"):
        print(f"截止      {acct['as_of']}")


def _session_file(args):
    path = config.session_path(getattr(args, "session", None))
    if not path.exists():
        raise RuntimeError(f"缺少 session.json（{path}），先运行 sgcc login")
    return path


def cmd_balance(args):
    path = _session_file(args)
    if args.ui:
        acct = device.balance_ui()
    else:
        plain = api.query(api.load_session(path))
        if args.raw:
            print(json.dumps(plain, ensure_ascii=False, indent=2))
            return 0
        acct = api.extract_account(plain)
    _show_account(acct, args.json)
    return 0


def cmd_refresh(args):
    from . import login as lg

    path = _session_file(args)
    token = lg.get_token()
    if not token:
        raise RuntimeError("未能从手机取到登录凭证")
    lg.update_session(path, token)
    if not args.json:
        print(f"token: {token}")
        print(f"session: {path}")
    acct = api.fetch(api.load_session(path))
    _show_account(acct, args.json)
    return 0


def cmd_login(args):
    from . import login as lg

    token = lg.do_login(force=args.force, code=args.code)
    path = lg.update_session(config.session_path(args.session), token)
    if not args.json:
        print(f"token: {token}")
        print(f"session: {path}")
    acct = api.fetch(api.load_session(path))
    _show_account(acct, args.json)
    return 0


def cmd_doctor(args):
    checks = []

    def check(name, fn, optional=False):
        try:
            checks.append({"check": name, "ok": True, "optional": optional, "detail": fn()})
        except Exception as e:
            checks.append({"check": name, "ok": False, "optional": optional, "detail": str(e)})

    def need(cond, msg):
        if not cond:
            raise RuntimeError(msg)
        return True

    check("python", lambda: sys.version.split()[0])
    path = config.session_path(args.session)
    check("session", lambda: (need(path.exists(), f"缺少 {path}"), str(path))[1])
    if path.exists():
        check("balance", lambda: f"¥{api.fetch(api.load_session(path))['balance']:.2f}")
    # 服务器上只跑 balance 时，没有 adb / 手机是正常的
    check("adb", lambda: (need(shutil.which("adb"), "PATH 里没有 adb（只有 refresh/login 需要）"), shutil.which("adb"))[1], optional=True)
    check("device", lambda: device.adb("get-state").stdout.strip() or "offline", optional=True)

    ok = all(c["ok"] for c in checks if not c["optional"])
    if args.json:
        _emit({"ok": ok, "checks": checks}, True)
    else:
        for c in checks:
            mark = "OK  " if c["ok"] else ("WARN" if c["optional"] else "FAIL")
            print(f"{mark} {c['check']:<8} {c['detail']}")
    return 0 if ok else 1


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--session", metavar="PATH", help="session.json 路径（默认 ~/.sgcc/session.json）")
    common.add_argument("--json", action="store_true", help="JSON 输出")

    ap = argparse.ArgumentParser(
        prog="sgcc",
        description="电费余额查询：凭证过期自动重新登录刷新。",
        epilog="示例: sgcc balance --json | sgcc login | sgcc refresh | sgcc doctor",
    )
    ap.add_argument("-V", "--version", action="version", version=f"sgcc {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    b = sub.add_parser("balance", parents=[common], help="查询余额（纯 HTTP，约 1 秒）")
    b.add_argument("--ui", action="store_true", help="改用 ADB UI 兜底（会操作手机界面）")
    b.add_argument("--raw", action="store_true", help="打印解密后的原始响应")
    b.set_defaults(func=cmd_balance)

    r = sub.add_parser("refresh", parents=[common], help="从手机读取新凭证写回 session")
    r.set_defaults(func=cmd_refresh)

    l = sub.add_parser("login", parents=[common], help="一条龙：登录(如需) + 刷新 token + 验证")
    l.add_argument("--force", action="store_true", help="清应用数据后强制重新登录")
    l.add_argument("--code", help="短信验证码（仅在风控要求时）")
    l.set_defaults(func=cmd_login)

    d = sub.add_parser("doctor", parents=[common], help="环境自检")
    d.set_defaults(func=cmd_doctor)

    return ap


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    try:
        return args.func(args)
    except Exception as e:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"错误：{e}", file=sys.stderr)
        return 1

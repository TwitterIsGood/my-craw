"""邦克 SafeKB 安全键盘自动映射与输入。

安全键盘是独立窗口（720x533，ty=2），uiautomator 看不到按键；`input text`
只改显示、不改安全缓冲，提交用的是缓冲——必须 sendevent 点按。

几何（固定，720x1280 设备）：
- 数字行 y=880、字母行 y=950：键中心 x = 36 + 72k（10 键）
- 字母行 y=1050：键中心 x = 72 + 72k（9 键，半键错位）
- 字母行 y=1150：键中心 x = 144 + 72k（7 键），左端 (36,1150)=锁定大写，
  右端 (684,1150)=退格
- 字符布局每次会话随机，因此每次输入前都要探测

清空：密码框右侧的 × 按钮 (518,729) 会同时清显示和安全缓冲（键盘 DEL
也行，但 × 更稳）。切记 20 字符上限：满了之后按键静默失效。

明文 oracle：点「显示密码」后密码框 password="false"，dump 里 text 为明文。
"""

import os
import re
import subprocess
import time

ENV = dict(os.environ, MSYS_NO_PATHCONV="1")
EV = os.environ.get("SGCC_INPUT_EV", "/dev/input/event1")
RID_PWD = "user_activity_input_pwd_et"
PLACEHOLDER = "请输入密码"
DUMP_PATH = "/sdcard/uk.xml"

DIGIT_X = [36 + 72 * k for k in range(10)]
ROW2_X = [72 + 72 * k for k in range(9)]
ROW3_X = [144 + 72 * k for k in range(7)]
GRID = [(880, DIGIT_X), (950, DIGIT_X), (1050, ROW2_X), (1150, ROW3_X)]

SHIFT_POS = (36, 1150)
DEL_POS = (684, 1150)
XICON = (518, 729)
SHOW_PWD = (610, 729)


def adb(*args, timeout=40):
    return subprocess.run(
        ["adb", *args],
        env=ENV,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def tap(x, y, dur=0.08):
    seq = (
        f"sendevent {EV} 3 47 0; sendevent {EV} 3 57 7; sendevent {EV} 3 48 8; "
        f"sendevent {EV} 3 53 {x}; sendevent {EV} 3 54 {y}; "
        f"sendevent {EV} 1 330 1; sendevent {EV} 0 0 0; sleep {dur}; "
        f"sendevent {EV} 3 57 -1; sendevent {EV} 1 330 0; sendevent {EV} 0 0 0"
    )
    adb("shell", seq)


def dump():
    adb("shell", f"uiautomator dump --compressed {DUMP_PATH} >/dev/null 2>&1")
    return adb("exec-out", f"cat {DUMP_PATH}").stdout


def read_pwd(xml=None):
    s = xml if xml is not None else dump()
    m = re.search(r'resource-id="[^"]*' + RID_PWD + r'"[^>]*?text="([^"]*)"', s)
    if not m:
        m = re.search(r'text="([^"]*)"[^>]*resource-id="[^"]*' + RID_PWD + r'"', s)
    t = m.group(1) if m else ""
    return "" if t == PLACEHOLDER else t


def kb_open():
    out = adb("shell", "dumpsys window windows | grep -c '720x533'").stdout
    try:
        return int(out.strip().splitlines()[-1]) > 0
    except (ValueError, IndexError):
        return False


def is_masked(xml=None):
    s = xml if xml is not None else dump()
    m = re.search(r"<node[^>]*" + RID_PWD + r"[^>]*>", s)
    if not m:
        return None
    a = re.search(r'password="(\w+)"', m.group(0))
    return a.group(1) == "true" if a else None


def show_plaintext():
    """确保密码以明文形式暴露给 uiautomator。"""
    xml = dump()
    if is_masked(xml) is False:
        return True
    b = re.search(r"<node[^>]*user_activity_show_pwd_img[^>]*>", xml)
    if not b:
        return False
    box = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', b.group(0))
    x = (int(box.group(1)) + int(box.group(3))) // 2
    y = (int(box.group(2)) + int(box.group(4))) // 2
    adb("shell", f"input tap {x} {y}")
    time.sleep(0.8)
    return is_masked() is False


def clear():
    """点密码框的 × 按钮，清显示和安全缓冲。空框时点该处只是聚焦。"""
    adb("shell", f"input tap {XICON[0]} {XICON[1]}")
    time.sleep(0.28)


def probe(pos):
    """清空后点一下 pos，返回产生的字符（可能为空）。"""
    clear()
    tap(*pos)
    time.sleep(0.32)
    s = read_pwd()
    clear()
    return s


def find_keys(needed=None, verbose=False):
    """扫描数字行和三个字母行，返回 {char: (x,y)}（小写归一）。"""
    need = set(needed or [])
    found = {}
    for y, xs in GRID:
        for x in xs:
            s = probe((x, y))
            if len(s) == 1:
                c = s.lower()
                if c not in found:
                    found[c] = (x, y)
                    if verbose:
                        print(f"  {x},{y} -> {s!r}", flush=True)
            if need and need <= set(found):
                return found
    return found


def caps_on(letter_pos):
    """通过已知字母键判断当前是否大写模式。"""
    s = probe(letter_pos)
    return s.isupper() if s else None


def set_caps(letter_pos, want_upper):
    for _ in range(2):
        cur = caps_on(letter_pos)
        if cur == want_upper:
            return True
        tap(*SHIFT_POS)
        time.sleep(0.25)
    return caps_on(letter_pos) == want_upper


def type_text(text, pos_of):
    """pos_of: {char(lower): (x,y)}；自动切换大小写。返回读回内容。"""
    for ch in dict.fromkeys(c.lower() for c in text):
        if ch not in pos_of:
            raise KeyError(f"布局里没有字符 {ch!r}")
    first_letter = next(p for c, p in pos_of.items() if c.isalpha())
    caps = caps_on(first_letter)
    if caps is None:
        raise RuntimeError("无法确定大小写状态")
    for ch in text:
        want = ch.isupper()
        if want != caps:
            tap(*SHIFT_POS)
            time.sleep(0.22)
            caps = want
        tap(*pos_of[ch.lower()])
        time.sleep(0.16)
    return read_pwd()


def main():
    import argparse
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="python -m sgcc.safekb")
    ap.add_argument("--map", action="store_true", help="只探测并打印布局")
    ap.add_argument("--type", help="探测布局后输入的文本")
    args = ap.parse_args()

    if not kb_open():
        print("键盘未打开", file=sys.stderr)
        return 1
    show_plaintext()
    keys = find_keys(verbose=args.map)
    print(f"keys={len(keys)} shift={SHIFT_POS} del={DEL_POS}")
    if args.map:
        for c, pos in sorted(keys.items(), key=lambda kv: (kv[1][1], kv[1][0])):
            print(f"  {pos[0]},{pos[1]} = {c!r}")
    if args.type:
        clear()
        got = type_text(args.type, keys)
        print(f"typed: {got!r} ok={got == args.type}")
        return 0 if got == args.type else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

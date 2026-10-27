---
name: sgcc
description: >-
  Query electricity bill balance and account info for a home meter.
  Use when the user asks about 电费, 电量, 余额, 欠费, 交电费, "how much power
  credit is left", or when a previous balance query failed with an expired token.
---

# 电费余额查询

查询余额、可用余额与账单截止时间。

## 快速使用

脚本目录：`${CLAUDE_SKILL_DIR}/scripts`（下文命令都在该目录执行；已安装时也可直接用 `sgcc` 命令）。

Windows 上不依赖 Python 时可用自带的 `scripts/sgcc.exe`，参数完全相同：

```bash
python entry.py balance          # 人类可读余额
python entry.py balance --json   # JSON：balance/available/account_no/address/as_of
python entry.py doctor           # 环境自检
python entry.py refresh          # 凭证过期：短信验证码重新登录
python entry.py login            # 短信验证码登录（提示输入验证码）
python entry.py login --code 123456   # 非交互：直接传验证码

./sgcc.exe balance --json        # Windows 二进制（等价）
```

`balance --ui` 是兜底：通过手机读取余额（约 20 秒），接口不通时再用。

## 前置条件

- `session.json` 存在（默认 `~/.sgcc/session.json`，或 `--session PATH` / `$SGCC_SESSION`），缺失时 `balance` 无法工作。
- 客户端密钥：`$SGCC_CLIENT_PRIV` 或 `~/.sgcc/crypto.json` 的 `client_priv`（64 位 hex），缺失时 `balance` 报错提示。
- `login` / `refresh` 只用短信验证码，不需要手机或 `adb`；验证码发到手机号，从 `~/.sgcc/config.json` 的 `phone` 或 `SGCC_PHONE` 读。
- 需要 `login --ui` / `balance --ui` 时：`adb` 在 PATH、手机已连接且解锁。

## 工作流

1. 用户问电费 → 先 `python entry.py balance --json`。
2. 返回 `{"error": ...}` 或服务端报登录状态失效 → `python entry.py login`（会发短信，等用户报 6 位验证码）。
3. `login` 失败（验证码错/超时）→ 重跑一次，会给用户发新短信。
4. 仍失败 → `python entry.py balance --ui` 兜底拿到数字，再排查设备连接。

## 输出字段

`balance`（分转元后的值）为账户余额；`available` 为可用余额；`as_of` 是账单截止时间。

## 注意

- 短间隔（<5 秒）重复查询会被限流，脚本已内置节流与退避，不要并行跑多个 `balance`。
- `login --force` 会清空本地登录状态，可能需要短信验证码；不要连续试错密码。
- 不要把 `session.json`、`crypto.json`、账号密码写进仓库或日志。

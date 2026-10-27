# sgcc-balance

网上国网电费余额命令行工具。查询自己户号的表内余额、可用余额和账单截止时间。

```
$ sgcc balance
表内余额  ¥0.00
户号      1234567890123
地址      北京市某某区******101
截止      2026年1月1日 00:00:00
```

## 安装

Windows / Linux / macOS 任选一种：

**1. 独立二进制（不需要 Python）**

从 GitHub Releases 下载对应文件：

- `sgcc-windows-x64.exe`
- `sgcc-linux-x64`
- `sgcc-macos-arm64`

```bash
chmod +x sgcc-linux-x64 && ./sgcc-linux-x64 balance
```

自己打包：`pip install -e ".[build]" && python build.py --exe` → `dist/sgcc(.exe)`。
打 tag（`v0.1.0`）会自动构建三平台二进制、发布 Release，并上传 PyPI。

**2. pip / pipx / uv（推荐，随系统 Python）**

```bash
pipx install sgcc-balance     # 隔离环境，命令名 sgcc
# 或
uv tool install sgcc-balance
# 或
pip install sgcc-balance
```

**3. 源码**

```bash
pip install -e .
python -m sgcc balance        # 不安装也能用
```

> 三个平台功能一致：`balance` 只依赖网络；`login` / `refresh` / `balance --ui` 另外要求 `adb` 在 PATH。

## 命令

| 命令 | 作用 |
| --- | --- |
| `sgcc balance` | 查询余额（默认） |
| `sgcc balance --json` | JSON 输出，便于脚本消费 |
| `sgcc balance --raw` | 打印原始响应 |
| `sgcc balance --ui` | 连接手机操作 App 读取（约 20 秒） |
| `sgcc refresh` | 刷新登录凭证 |
| `sgcc login` | 完整登录流程并刷新凭证 |
| `sgcc login --force` | 重置后重新登录 |
| `sgcc login --code 123456` | 登录需要短信验证码时传入 |
| `sgcc doctor` | 环境自检 |

通用参数：`--session PATH` 指定 session 文件，`--json` 输出 JSON。

## 配置

`~/.sgcc/` 目录下：

- `session.json` — 登录状态（含凭证，不要提交或外传）
- `config.json` — 账号密码，仅 `sgcc login` 真正重登时使用
- `crypto.json` — 客户端密钥，需自备（见下）

```json
// ~/.sgcc/config.json
{
  "phone": "1xxxxxxxxxx",
  "password": "your-password"
}
```

环境变量：

- `SGCC_HOME`：配置目录，默认 `~/.sgcc`
- `SGCC_SESSION`：session 文件完整路径
- `SGCC_PHONE` / `SGCC_PASSWORD`：等价于 config.json
- `SGCC_CLIENT_PRIV`：客户端密钥（64 位 hex），见下节
- `SGCC_INPUT_EV`：安全键盘输入设备，默认 `/dev/input/event1`

## 客户端密钥

响应需要客户端密钥才能解出明文。该密钥不随本仓库分发，请自行准备：

```bash
export SGCC_CLIENT_PRIV=<64 位 hex>
# 或
echo '{"client_priv": "<64 位 hex>"}' > ~/.sgcc/crypto.json
```

缺失或格式不对时，`sgcc balance` 会直接报错并提示这里。

## 部署到服务器 / 其他机器

准备一次 `session.json` 之后，日常查询可以脱离手机：

```bash
pipx install sgcc-balance
mkdir -p ~/.sgcc && scp phonepc:~/.sgcc/session.json ~/.sgcc/
cp ~/.sgcc/crypto.json ~/.sgcc/        # 密钥一并同步
sgcc doctor      # adb/device 显示 WARN 属正常
sgcc balance --json
```

注意：

- 服务器时钟要准（请求带毫秒时间戳），建议开 NTP。
- 需要能直连服务域名（不要走会改 `Host` / `Content-Length` 的反向代理）。

登录状态会过期。过期后在连着手机的机器上跑 `sgcc refresh`，再把 `~/.sgcc/session.json` 同步过去即可：

```bash
# cron：每小时试一次，失败就刷新并推给服务器
0 * * * * cd ~ && /usr/local/bin/sgcc balance --json >/dev/null || \
  /usr/local/bin/sgcc refresh && rsync -az ~/.sgcc/session.json server:~/.sgcc/
```

## 开发与发布

```bash
pip install -e ".[build,test]"
python -m unittest discover -s tests -v   # 平台无关单测，CI 在 Linux/Windows/macOS 上跑
python build.py --exe                     # 本地打包
python build.py --sync-skill              # 同步到 ~/.claude/skills/sgcc
```

发布：

```bash
git tag v0.1.0 && git push origin v0.1.0
```

CI 会构建三平台二进制、发 GitHub Release，并通过 PyPI Trusted Publishing 上传（需在 PyPI 项目设置里绑定此仓库与 `pypi` environment）。

## 说明

- 本项目仅供个人查询自己户号的账单使用。
- 界面自动化相关的坐标常量按特定机型实测，其它机型需自行调整。

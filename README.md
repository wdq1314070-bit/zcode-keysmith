<!-- markdownlint-disable MD013 MD033 MD041 -->

<p align="center">
  <img src="docs/assets/readme/zcode-keysmith-preview.png" alt="Illustrative zcode-keysmith install preview; actual paths and output vary" width="100%">
</p>
<p align="center"><em>Illustrative preview / 示意预览；实际路径与输出以本机 dry-run 为准。</em></p>

<h1 align="center">zcode-keysmith</h1>

<p align="center">先预览、再写入、可撤销的 ZCode App system-role 入口安装器。</p>

<p align="center">
  <img alt="Source version v0.1.0" src="https://img.shields.io/badge/source-v0.1.0-0099CC">
  <img alt="License MIT" src="https://img.shields.io/badge/license-MIT-6DB33F">
</p>

<p align="center">
  <a href="#简体中文">简体中文</a> ·
  <a href="README.en.md">English</a> ·
  <a href="docs/reference.md">Reference</a> ·
  <a href="docs/agent-install.md">智能体安装 / Agent install</a> ·
  <a href="LICENSE">License</a>
</p>

## 简体中文

> [!NOTE]
> 本仓库是 [Jia-Ethan/zcode-keysmith](https://github.com/Jia-Ethan/zcode-keysmith) 的 fork，在原版 macOS 支持之外**新增了 Windows 支持**。上游仅源码发布，本仓库同步上游 `v0.1.0` 内容并维护 `zcode-keysmith-win.py`。

Keysmith 系列为本地 AI 工具**安全部署、验证和撤销**自定义指令。`zcode-keysmith` 在用户目录安装受管理的 `system-role.md`，经 agent-server wrapper 进入 ZCode runtime 的 system message 路径。**不是** `AGENTS.md` 安装器；`v0.1.0` 仅发布源码，无 Desktop 客户端。

> [!WARNING]
> 这会改本机 ZCode 的 **agent-server 入口**，影响之后新启动的会话。不改 App 原包，不读 API key / provider / MCP。支持 macOS 与 Windows。默认只预览，显式 `--yes` 才写入。先阅读 [`examples/system-role.md`](examples/system-role.md) 和 [`docs/reference.md`](docs/reference.md)。

### 选择哪个 Keysmith

| 项目 | 目标工具 | 部署面 | 稳妥安装 | Desktop |
| --- | --- | --- | --- | --- |
| [codex-keysmith](https://github.com/Jia-Ethan/codex-keysmith) | Codex | 全局 `~/.codex` 指令 | 稳定 CLI Release | 未签名 Beta |
| [claude-keysmith](https://github.com/Jia-Ethan/claude-keysmith) | Claude Code | 项目 / 用户 `CLAUDE.md` import | 源码 CLI | 未签名 Beta |
| [grok-keysmith](https://github.com/Jia-Ethan/grok-keysmith) | Grok Build | 全局 `~/.grok/rules`（不改 `AGENTS.md`） | 稳定 CLI Release | 未签名 Beta |
| **[zcode-keysmith（本仓库，含 Windows）](https://github.com/wdq1314070-bit/zcode-keysmith)** | ZCode App | 用户目录 system-role + wrapper | 仅源码 | 无 |

### 安装方式

**只有源码安装。** 使用上游 [`v0.1.0`](https://github.com/Jia-Ethan/zcode-keysmith/releases/tag/v0.1.0) 的 GitHub 自动源码归档，或 clone 本仓库后运行 `python3 zcode-keysmith.py`（macOS）/ `python3 zcode-keysmith-win.py`（Windows）。没有独立二进制资产、没有 `pip` / npm、没有本仓库 GUI。

### 快速开始

```bash
git clone https://github.com/wdq1314070-bit/zcode-keysmith.git
cd zcode-keysmith
# macOS
python3 zcode-keysmith.py --version
python3 zcode-keysmith.py install --dry-run
python3 zcode-keysmith.py install --yes
python3 zcode-keysmith.py doctor

# Windows
python3 zcode-keysmith-win.py --version
python3 zcode-keysmith-win.py install --dry-run
python3 zcode-keysmith-win.py install --yes
python3 zcode-keysmith-win.py doctor
```

退出并重新打开 ZCode，新建任务后再运行 `python3 zcode-keysmith.py verify`（macOS）或 `python3 zcode-keysmith-win.py verify`（Windows）。非默认 App 路径用 `--zcode-app` 或 `ZCODE_APP_PATH`。`install --dry-run` 仍需能读到可打补丁的本机 runtime。

### Windows 支持

Windows 版使用 `zcode-keysmith-win.py`（macOS 版逻辑的 Windows 移植）：

```bash
python3 zcode-keysmith-win.py install --dry-run   # 先看写入计划
python3 zcode-keysmith-win.py install --yes        # 确认后写入
python3 zcode-keysmith-win.py doctor               # 检查状态
python3 zcode-keysmith-win.py verify                # 检查链路
python3 zcode-keysmith-win.py uninstall --yes      # 卸载
```

与 macOS 版的差异：

- **持久化机制**：macOS 用 `launchctl setenv` + LaunchAgent plist；Windows 写 `HKCU\Environment` 用户环境变量（Explorer 登录时自动加载，等价于用户级 LaunchAgent），旧值备份到 `~/.zcode-keysmith/backups/env-backup-*.json`。写入后广播 `WM_SETTINGCHANGE`。
- **入口命令**：Windows 的 Node `spawn` 不能直接执行 `.py` 文件（无 shebang），所以 `ZCODE_AGENT_SERVER_COMMAND` 指向 `python.exe`，wrapper 路径放进 `ZCODE_AGENT_SERVER_ARGS_JSON`：`["<managed>\\bin\\zcode-agent-wrapper.py","app-server","--stdio"]`。
- **stdio 管道**：Windows 管道上 `subprocess.run` 继承句柄不稳定（agent 启动约 1.5s 即退出，报 `ZCode agent transport closed`）；`BufferedReader.read(n)` 会阻塞到读满 n 字节（请求被卡 180s 直到超时）。因此 wrapper 使用 `subprocess.Popen` + 三个中继线程，读取用 `os.read(fd, 65536)`（Windows 管道一有数据立即返回）。
- **ZCode 路径自动发现**：依次检查 `ZCODE_APP_PATH` 环境变量、注册表 Uninstall 键、`%LOCALAPPDATA%\Programs\ZCode`、`%ProgramFiles%\ZCode`、`D:\ZCode`。
- **无 LaunchAgent**：Windows 不生成 plist；`~/.zcode-keysmith/bin/zcode-keysmith-env.sh` 也不需要（macOS 专属）。

其余逻辑与 macOS 版一致：ZCode App 原包不被修改（`app_bundle_modified: false`）、runtime 缓存在用户目录打补丁、`wrapper-start.jsonl` 日志、API key/token/MCP/provider 配置由 ZCode 自身管理（安装器不读取、不保存、不打印）。

### 会修改什么

macOS 的受管理路径与行为：

| 路径 | 会发生什么 |
| --- | --- |
| `~/.zcode-keysmith/system-role.md` | 写入归一化后的源提示词 |
| `~/.zcode-keysmith/config.json`、`bin/*` | 受管理配置与 wrapper |
| `~/Library/LaunchAgents/com.jia.zcode-keysmith.env.plist` | 用户 LaunchAgent |
| `cache/`、`logs/` | 运行时缓存与 wrapper 日志；卸载不删 |

Windows 版无 LaunchAgent，持久化走 `HKCU\Environment` 用户环境变量（详见上文「Windows 支持」）。不写项目文件，不改 `ZCode.app`。原理见 [`docs/reference.md`](docs/reference.md)。

### 如何撤销

```bash
# macOS
python3 zcode-keysmith.py uninstall --dry-run
python3 zcode-keysmith.py uninstall --yes

# Windows
python3 zcode-keysmith-win.py uninstall --dry-run
python3 zcode-keysmith-win.py uninstall --yes
```

卸载只把受管理文件改名为 `.bak_*`，并清空当前 launchd / HKCU 环境。没有 `recover` / `restore`；手工回滚需重新加载恢复后的 env 脚本并重启 ZCode，完整步骤见 [`docs/reference.md`](docs/reference.md)。

### 平台与 Beta 限制

文档化支持为 macOS（本机 `ZCode.app`）与 Windows（本仓库新增）。`v0.1.0` Release 仅提供 GitHub 自动源码归档；无签名包、无 Desktop Beta。推荐 Python 3.10+。

### 进阶文档 · 贡献 · 系列

原理、字段与卸载残留见 [`docs/reference.md`](docs/reference.md)；智能体安装见 [`docs/agent-install.md`](docs/agent-install.md)。提交前运行 `python3 -m py_compile zcode-keysmith.py`、`python3 -m py_compile zcode-keysmith-win.py` 与 `python3 -m pytest tests -q`。安装器不读取 API key。社区：[LINUX DO](https://linux.do)。核心系列只有对照表中的四个项目；本仓库为该系列 ZCode 一项的 Windows 增强 fork。

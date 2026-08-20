<!-- markdownlint-disable MD013 MD033 MD041 -->

<p align="center">
  <img src="docs/assets/readme/zcode-keysmith-preview.png" alt="Illustrative zcode-keysmith install preview; actual paths and output vary" width="100%">
</p>
<p align="center"><em>Illustrative preview / 示意预览；actual paths and output follow the local dry-run.</em></p>

<h1 align="center">zcode-keysmith</h1>

<p align="center">Preview-first ZCode App system-role entrypoint you can verify and undo.</p>

<p align="center">
  <img alt="Source version v0.1.0" src="https://img.shields.io/badge/source-v0.1.0-0099CC">
  <img alt="License MIT" src="https://img.shields.io/badge/license-MIT-6DB33F">
</p>

<p align="center">
  <a href="README.md">简体中文</a> ·
  <a href="#english">English</a> ·
  <a href="docs/reference.md">Reference</a> ·
  <a href="docs/agent-install.md">Agent install</a> ·
  <a href="LICENSE">License</a>
</p>

## English

> [!NOTE]
> This repository is a fork of [Jia-Ethan/zcode-keysmith](https://github.com/Jia-Ethan/zcode-keysmith) that **adds Windows support** on top of the original macOS implementation. Upstream is source-only; this repo tracks upstream `v0.1.0` and maintains `zcode-keysmith-win.py`.

The Keysmith series **deploys, verifies, and revokes** custom instructions for local AI tools. `zcode-keysmith` installs a managed `system-role.md` in the user directory and routes it through an agent-server wrapper into ZCode's runtime system-message path. It is **not** an `AGENTS.md` installer; `v0.1.0` is source-only, with no Desktop client.

> [!WARNING]
> This changes the local ZCode **agent-server entrypoint** for later newly started sessions. The app bundle stays untouched; API keys, provider settings, and MCP are never read. macOS and Windows are supported. Commands preview unless you pass `--yes`. Read [`examples/system-role.md`](examples/system-role.md) and [`docs/reference.md`](docs/reference.md) first.

### Which Keysmith to use

| Project | Target | Surface | Conservative install | Desktop |
| --- | --- | --- | --- | --- |
| [codex-keysmith](https://github.com/Jia-Ethan/codex-keysmith) | Codex | Global `~/.codex` instructions | Stable CLI Release | Unsigned Beta |
| [claude-keysmith](https://github.com/Jia-Ethan/claude-keysmith) | Claude Code | Project / user `CLAUDE.md` import | Source CLI | Unsigned Beta |
| [grok-keysmith](https://github.com/Jia-Ethan/grok-keysmith) | Grok Build | Global `~/.grok/rules` (does not edit `AGENTS.md`) | Stable CLI Release | Unsigned Beta |
| **[zcode-keysmith (this repo, with Windows)](https://github.com/wdq1314070-bit/zcode-keysmith)** | ZCode App | User-dir system-role + wrapper | Source only | None |

### Install options

**Source install only.** Use the GitHub-generated source archive from upstream [`v0.1.0`](https://github.com/Jia-Ethan/zcode-keysmith/releases/tag/v0.1.0), or clone this repo and run `python3 zcode-keysmith.py` (macOS) / `python3 zcode-keysmith-win.py` (Windows). There are no standalone binary assets, no pip/npm package, and no GUI in this repository.

### Quick start

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

Quit and reopen ZCode, start a fresh task, then run `python3 zcode-keysmith.py verify` (macOS) or `python3 zcode-keysmith-win.py verify` (Windows). Use `--zcode-app` or `ZCODE_APP_PATH` for a non-default app. `install --dry-run` still needs a local patchable runtime.

### Windows support

On Windows, use `zcode-keysmith-win.py` (a Windows port of the macOS installer):

```bash
python3 zcode-keysmith-win.py install --dry-run   # preview writes
python3 zcode-keysmith-win.py install --yes        # confirm and write
python3 zcode-keysmith-win.py doctor               # check status
python3 zcode-keysmith-win.py verify                # check the chain
python3 zcode-keysmith-win.py uninstall --yes      # remove
```

Differences from the macOS version:

- **Persistence**: macOS uses `launchctl setenv` + a LaunchAgent plist; Windows writes `HKCU\Environment` user environment variables (Explorer reloads them at login, equivalent to a user-level LaunchAgent). Previous values are backed up to `~/.zcode-keysmith/backups/env-backup-*.json`, and a `WM_SETTINGCHANGE` broadcast is sent after writing.
- **Entry command**: Node `spawn` on Windows cannot execute a `.py` file directly (no shebang), so `ZCODE_AGENT_SERVER_COMMAND` points at `python.exe` and the wrapper path goes into `ZCODE_AGENT_SERVER_ARGS_JSON`: `["<managed>\\bin\\zcode-agent-wrapper.py","app-server","--stdio"]`.
- **stdio pipes**: On Windows, `subprocess.run` with inherited handles is unreliable (agent exits after ~1.5s with `ZCode agent transport closed`), and `BufferedReader.read(n)` blocks until n bytes or EOF arrive (requests stall for 180s until the desktop side times out). The wrapper therefore uses `subprocess.Popen` plus three relay threads reading with `os.read(fd, 65536)`, which returns as soon as any data is available on a Windows pipe.
- **ZCode discovery**: checks `ZCODE_APP_PATH`, registry Uninstall keys, `%LOCALAPPDATA%\Programs\ZCode`, `%ProgramFiles%\ZCode`, and `D:\ZCode`.
- **No LaunchAgent**: no plist is generated on Windows, and `zcode-keysmith-env.sh` (macOS-only) is not installed.

Everything else matches the macOS version: the ZCode app bundle is not modified (`app_bundle_modified: false`), the runtime is patched in a user-directory cache, `wrapper-start.jsonl` logging, and API keys/tokens/MCP/provider config stay managed by ZCode itself (the installer never reads, stores, or prints them).

### What it changes

Managed paths and behavior on macOS:

| Path | What happens |
| --- | --- |
| `~/.zcode-keysmith/system-role.md` | Normalized source prompt |
| `~/.zcode-keysmith/config.json`, `bin/*` | Managed config and wrapper |
| `~/Library/LaunchAgents/com.jia.zcode-keysmith.env.plist` | User LaunchAgent |
| `cache/`, `logs/` | Runtime cache and wrapper logs; not removed on uninstall |

On Windows there is no LaunchAgent; persistence goes through `HKCU\Environment` user environment variables (see "Windows support" above). No project files are written; `ZCode.app` is not modified. Design: [`docs/reference.md`](docs/reference.md).

### How to undo

```bash
# macOS
python3 zcode-keysmith.py uninstall --dry-run
python3 zcode-keysmith.py uninstall --yes

# Windows
python3 zcode-keysmith-win.py uninstall --dry-run
python3 zcode-keysmith-win.py uninstall --yes
```

Uninstall only renames the managed files to `.bak_*` and clears the current launchd (`macOS`) or `HKCU\Environment` (`Windows`) entrypoint. There is no `recover` / `restore`; manual rollback must also reload the restored env script and restart ZCode. Full steps: [`docs/reference.md`](docs/reference.md).

### Platforms and Beta limits

Documented support is macOS (a local `ZCode.app`) and Windows (added in this repo). The `v0.1.0` Release provides only GitHub-generated source archives; there is no signed installer or Desktop Beta. Recommended Python 3.10+.

### Advanced docs, contributing, and the series

Design, fields, and uninstall leftovers: [`docs/reference.md`](docs/reference.md). Agent install: [`docs/agent-install.md`](docs/agent-install.md). Before a patch, run `python3 -m py_compile zcode-keysmith.py`, `python3 -m py_compile zcode-keysmith-win.py`, and `python3 -m pytest tests -q`. The installer never reads API keys. Community: [LINUX DO](https://linux.do). The core series is only the four projects in the table above; this repo is the Windows-enhanced fork of the ZCode entry in that series.

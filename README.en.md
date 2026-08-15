# zcode-keysmith

<p align="center">
  <strong>ZCode App managed true system-role entrypoint.</strong>
</p>

<p align="center">
  <a href="README.md">简体中文</a> ·
  <a href="#english">English</a> ·
  <a href="docs/reference.md">Reference</a> ·
  <a href="docs/agent-install.md">Agent install</a> ·
  <a href="LICENSE">License</a>
</p>

## English

### What this is

`zcode-keysmith` installs a managed true system-role entrypoint for the local ZCode desktop app. It installs the repository's `examples/system-role.md` as a managed copy in the user directory, and routes it into ZCode's runtime `customSystemPrompt` path so a newly started agent-server process picks it up as a system message. **The ZCode app bundle remains untouched**: the installer only writes to the user directory and a user LaunchAgent. API keys, provider settings, MCP settings, and project files stay under ZCode's own management; the installer never reads, stores, or prints them.

Default managed files:

```text
~/.zcode-keysmith/system-role.md
~/.zcode-keysmith/config.json
~/.zcode-keysmith/bin/zcode-agent-wrapper.py
~/.zcode-keysmith/bin/zcode-keysmith-env.sh
~/Library/LaunchAgents/com.jia.zcode-keysmith.env.plist
```

### How it works

The ZCode desktop app reads two environment variables when starting agent-server:

```text
ZCODE_AGENT_SERVER_COMMAND
ZCODE_AGENT_SERVER_ARGS_JSON
```

`zcode-keysmith` points `ZCODE_AGENT_SERVER_COMMAND` at `~/.zcode-keysmith/bin/zcode-agent-wrapper.py`. The wrapper does three things:

1. Reads ZCode's bundled runtime: `/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs`;
2. Caches a copy of the runtime in the user directory, patching only the `customSystemPrompt` entrypoint to prefer `~/.zcode-keysmith/system-role.md`;
3. Launches the cached runtime with ZCode's own Electron node command, preferring the bundled `ZCode Helper` executable so the background agent-server is not shown as another foreground ZCode app in the Dock; it falls back to the main executable only when no Helper binary is present.

The ZCode runtime places `customSystemPrompt` into an `injectionTarget: "system"` context segment, so `system-role.md` lands in ZCode's system message path rather than as an ordinary project instruction file. During install, the source prompt is normalized once: if `examples/system-role.md` comes from a GLM ChatML export, the outer `<|im_start|>system:` / `<|im_end|>` transport markers are cleaned, and only the system prompt body is written.

### Install

```bash
python3 zcode-keysmith.py install --dry-run   # preview
python3 zcode-keysmith.py install --yes        # confirm and write
python3 zcode-keysmith.py doctor               # check state
python3 zcode-keysmith.py verify                # check the wiring
```

Existing managed files are backed up as `<filename>.bak_YYYYMMDD_HHMMSS`. `--dry-run` takes precedence even if `--yes` is also passed.

The installer updates the current macOS launchd environment and writes a user LaunchAgent so subsequent login sessions restore the same variables. **Any already-open ZCode process must be reopened** to inherit the new agent-server entrypoint. After install:

1. Quit and reopen ZCode;
2. Start a new task, type "Who are you?";
3. Run `python3 zcode-keysmith.py verify`; `wrapper_invoked: true` confirms ZCode actually launched the managed wrapper.

Full field reference and `doctor`/`verify` output: [`docs/reference.md`](docs/reference.md).

### Windows support

On Windows, use `zcode-keysmith-win.py` (a Windows port of the macOS installer):

```bash
python3 zcode-keysmith-win.py install --dry-run   # preview
python3 zcode-keysmith-win.py install --yes        # confirm and write
python3 zcode-keysmith-win.py doctor               # check state
python3 zcode-keysmith-win.py verify                # check the wiring
python3 zcode-keysmith-win.py uninstall --yes      # uninstall
```

Differences from the macOS version:

- **Persistence**: macOS uses `launchctl setenv` + a LaunchAgent plist; Windows writes `HKCU\Environment` user environment variables (Explorer reloads them at login, equivalent to a user-level LaunchAgent). Previous values are backed up to `~/.zcode-keysmith/backups/env-backup-*.json`, and a `WM_SETTINGCHANGE` broadcast is sent after writing.
- **Entry command**: Node `spawn` on Windows cannot execute a `.py` file directly (no shebang), so `ZCODE_AGENT_SERVER_COMMAND` points at `python.exe` and the wrapper path goes into `ZCODE_AGENT_SERVER_ARGS_JSON`: `["<managed>\\bin\\zcode-agent-wrapper.py","app-server","--stdio"]`.
- **stdio pipes**: On Windows, `subprocess.run` with inherited handles is unreliable (agent exits after ~1.5s with `ZCode agent transport closed`), and `BufferedReader.read(n)` blocks until n bytes or EOF arrive (requests stall for 180s until the desktop side times out). The wrapper therefore uses `subprocess.Popen` plus three relay threads reading with `os.read(fd, 65536)`, which returns as soon as any data is available on a Windows pipe.
- **ZCode discovery**: checks `ZCODE_APP_PATH`, registry Uninstall keys, `%LOCALAPPDATA%\Programs\ZCode`, `%ProgramFiles%\ZCode`, and `D:\ZCode`.
- **No LaunchAgent**: no plist is generated on Windows, and `zcode-keysmith-env.sh` (macOS-only) is not installed.

Everything else matches the macOS version: the ZCode app bundle is never modified (`app_bundle_modified: false`), the runtime is cached and patched in the user directory, `wrapper-start.jsonl` logging, and API keys/tokens/MCP/provider config stay under ZCode's own management (the installer never reads, stores, or prints them).

### Uninstall

```bash
python3 zcode-keysmith.py uninstall --dry-run   # preview
python3 zcode-keysmith.py uninstall --yes        # confirm removal
```

Renames managed files to `.bak_YYYYMMDD_HHMMSS` and clears the keysmith entrypoint from the current launchd environment. The ZCode app bundle remains untouched.

### ZCode at a non-default path

```bash
python3 zcode-keysmith.py install --zcode-app /path/to/ZCode.app --dry-run
# or
ZCODE_APP_PATH=/path/to/ZCode.app python3 zcode-keysmith.py install --dry-run
```

### Project layout and verification

See [`docs/reference.md`](docs/reference.md) for the project layout and `py_compile`/`pytest` verification steps.

### Community

This project accepts monitoring and feedback from the LINUX DO community: [LINUX DO](https://linux.do)

Same series:

- [codex-keysmith](https://github.com/Jia-Ethan/codex-keysmith) - Versioned instruction deployment for local Codex CLI configuration with preview, hook isolation, interruption recovery, and layered uninstall.
- [claude-keysmith](https://github.com/Jia-Ethan/claude-keysmith) - Managed Claude Code `CLAUDE.md` import-block installer for local Markdown instruction files.
- [grok-keysmith](https://github.com/Jia-Ethan/grok-keysmith) - Global `AGENTS.md` instruction deployment for Grok Build with compat/hook isolation, interruption recovery, and layered uninstall.
- [zcode-keysmith](https://github.com/Jia-Ethan/zcode-keysmith) - Managed true system-role entrypoint for ZCode App; an agent-server wrapper routes `system-role.md` into the runtime `customSystemPrompt` system-message path.

---

简体中文版: [`README.md`](README.md)。Agent install prompt: [`docs/agent-install.md`](docs/agent-install.md).

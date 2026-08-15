#!/usr/bin/env python3
"""Windows port of zcode-keysmith: install a managed true-system prompt entrypoint
for the local ZCode App (Windows build).

The macOS version (zcode-keysmith.py) relies on launchd (launchctl setenv +
a LaunchAgent plist) and on shebang-based execution of the wrapper. Windows has
neither, so this port replaces those mechanisms:

  * launchctl setenv + LaunchAgent  ->  HKCU\\Environment user environment
    variables (written via winreg and broadcast with WM_SETTINGCHANGE). Explorer
    re-reads these on every login, which is the Windows equivalent of a user
    LaunchAgent.
  * shebang execution of the wrapper  ->  ZCODE_AGENT_SERVER_COMMAND points at
    python.exe, and the wrapper path is placed in ZCODE_AGENT_SERVER_ARGS_JSON.
    The ZCode main process spawns the command without a shell, so the command
    must be an executable, not a .py file.

Everything else mirrors the upstream installer: the ZCode app bundle is never
touched, the runtime is cached and patched in the user directory, and API keys,
tokens, cookies, MCP secrets and provider config stay under ZCode's own
management -- the installer never reads, stores or prints them.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import winreg
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE_SYSTEM_FILE = REPO_ROOT / "examples" / "system-role.md"
DEFAULT_MANAGED_DIR = Path.home() / ".zcode-keysmith"
DEFAULT_SYSTEM_FILE_NAME = "system-role.md"
DEFAULT_CONFIG_FILE_NAME = "config.json"
DEFAULT_WRAPPER_NAME = "zcode-agent-wrapper.py"
DEFAULT_ENV_VARS = [
    "ZCODE_AGENT_SERVER_COMMAND",
    "ZCODE_AGENT_SERVER_ARGS_JSON",
    "ZCODE_KEYSMITH_SYSTEM_FILE",
    "ZCODE_KEYSMITH_ORIGINAL",
    "ZCODE_KEYSMITH_NODE_COMMAND",
    "ZCODE_KEYSMITH_CACHE_DIR",
    "ZCODE_KEYSMITH_LOG_DIR",
]
DEFAULT_AGENT_ARGS_JSON_BASE = '["app-server","--stdio"]'
PATCH_NEEDLE = "customSystemPrompt:this.config.systemPrompt,language:"

ENV_KEY = r"Environment"
HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002


class KeysmithError(Exception):
    """User-facing installer error."""


@dataclass(frozen=True)
class InstallPaths:
    managed_dir: Path
    system_file: Path
    config_file: Path
    wrapper: Path
    log_dir: Path
    cache_dir: Path
    wrapper_log: Path
    backup_dir: Path


@dataclass(frozen=True)
class InstallPlan:
    paths: InstallPaths
    source_system_file: Path
    zcode_runtime: Path
    node_command: Path
    python_command: Path
    activate: bool


def expand_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def build_paths(managed_dir: Path) -> InstallPaths:
    managed_dir = expand_path(managed_dir)
    bin_dir = managed_dir / "bin"
    return InstallPaths(
        managed_dir=managed_dir,
        system_file=managed_dir / DEFAULT_SYSTEM_FILE_NAME,
        config_file=managed_dir / DEFAULT_CONFIG_FILE_NAME,
        wrapper=bin_dir / DEFAULT_WRAPPER_NAME,
        log_dir=managed_dir / "logs",
        cache_dir=managed_dir / "cache",
        wrapper_log=managed_dir / "logs" / "wrapper-start.jsonl",
        backup_dir=managed_dir / "backups",
    )


def resolve_bundle_paths(zcode_app: Path) -> tuple[Path, Path]:
    app = expand_path(zcode_app)
    runtime = app / "resources" / "glm" / "zcode.cjs"
    node = app / "ZCode.exe"
    return runtime.resolve(), node.resolve()


def registry_zcode_install_location() -> Path | None:
    hives = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, key_path in hives:
        try:
            key = winreg.OpenKey(hive, key_path)
        except OSError:
            continue
        try:
            for index in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub_key_name = winreg.EnumKey(key, index)
                except OSError:
                    break
                try:
                    with winreg.OpenKey(key, sub_key_name) as sub:
                        try:
                            display, _ = winreg.QueryValueEx(sub, "DisplayName")
                        except OSError:
                            display = ""
                        if display and "zcode" in str(display).lower():
                            try:
                                location, _ = winreg.QueryValueEx(sub, "InstallLocation")
                            except OSError:
                                location = ""
                            if location and Path(location).is_dir():
                                return expand_path(location)
                except OSError:
                    continue
        finally:
            key.Close()
    return None


def discover_zcode_app_path() -> Path:
    env_app = os.environ.get("ZCODE_APP_PATH")
    candidates: list[Path] = []
    if env_app:
        candidates.append(Path(env_app))
    found = registry_zcode_install_location()
    if found:
        candidates.append(found)
    candidates.extend(
        [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ZCode",
            Path(os.environ.get("LOCALAPPDATA", "")) / "ZCode",
            Path(os.environ.get("ProgramFiles", "")) / "ZCode",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "ZCode",
            Path("D:/ZCode"),
        ]
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return expand_path(candidate)
    return DEFAULT_ZCODE_APP.resolve()


DEFAULT_ZCODE_APP = discover_zcode_app_path()


def app_supports_agent_server_override(zcode_app: Path | None) -> bool:
    if not zcode_app:
        return False
    asar = zcode_app / "resources" / "app.asar"
    if not asar.exists() or not asar.is_file():
        return False
    try:
        return b"ZCODE_AGENT_SERVER_COMMAND" in asar.read_bytes()
    except OSError:
        return False


def is_zcode_running() -> bool:
    completed = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq ZCode.exe", "/NH"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return "ZCode.exe" in completed.stdout


def normalize_system_prompt_content(content: str) -> str:
    """Normalize common exported system-prompt wrappers into prompt body text."""
    leading = content[: len(content) - len(content.lstrip())]
    text = content.lstrip()
    prefixes = [
        "<|im_start|>system:<project_instructions>",
        "<|im_start|>system:",
        "<|im_start|>system",
    ]
    for prefix in prefixes:
        if text.startswith(prefix):
            rest = text[len(prefix):]
            if prefix.endswith("<project_instructions>"):
                text = "<project_instructions>" + rest
            else:
                text = rest.lstrip("\r\n")
            break
    stripped = text.rstrip()
    if stripped.endswith("<|im_end|>"):
        text = stripped[: -len("<|im_end|>")].rstrip() + "\n"
    return leading + text


def read_required_text(path: Path, label: str) -> str:
    if not path.exists():
        raise KeysmithError(f"{label} not found: {path}")
    if not path.is_file():
        raise KeysmithError(f"{label} is not a regular file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise KeysmithError(f"{label} must be UTF-8: {path}") from exc
    except OSError as exc:
        raise KeysmithError(f"Could not read {label}: {path}\nReason: {exc}") from exc
    if not text.strip():
        raise KeysmithError(f"{label} is empty: {path}")
    return text


def read_system_prompt_source(path: Path) -> str:
    text = normalize_system_prompt_content(read_required_text(path, "source system prompt"))
    if not text.strip():
        raise KeysmithError(f"source system prompt is empty after normalization: {path}")
    return text


def ensure_runtime_patchable(runtime_path: Path) -> None:
    runtime = read_required_text(runtime_path, "ZCode runtime")
    if PATCH_NEEDLE not in runtime:
        raise KeysmithError(
            "ZCode runtime entrypoint shape was not recognized.\n"
            f"Runtime: {runtime_path}\n"
            "The installer expected the runtime context builder anchor used by current ZCode releases."
        )


def build_system_prompt_expression(system_file: str) -> str:
    system_file_json = json.dumps(system_file, ensure_ascii=False)
    return (
        "(this.config.systemPrompt&&this.config.systemPrompt.trim()?this.config.systemPrompt:"
        "(()=>{try{let e=process.env.ZCODE_KEYSMITH_SYSTEM_FILE||"
        + system_file_json
        + ";let t=require(\"node:fs\");return t.existsSync(e)?t.readFileSync(e,\"utf8\"):void 0}catch{return void 0}})())"
    )


def build_patched_runtime_text(original_runtime: str, system_file: str) -> str:
    if PATCH_NEEDLE not in original_runtime:
        raise KeysmithError("ZCode runtime patch anchor not found")
    replacement = "customSystemPrompt:" + build_system_prompt_expression(system_file) + ",language:"
    return original_runtime.replace(PATCH_NEEDLE, replacement, 1)


def backup_existing(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.bak_{stamp}")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak_{stamp}_{counter}")
        counter += 1
    path.replace(backup)
    return backup


def atomic_write_text(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(content)
        tmp = Path(handle.name)
    if mode is not None:
        tmp.chmod(mode)
    tmp.replace(path)
    if mode is not None:
        path.chmod(mode)


def env_values(plan: InstallPlan) -> dict[str, str]:
    args_json = json.dumps([str(plan.paths.wrapper), "app-server", "--stdio"], ensure_ascii=False)
    return {
        "ZCODE_AGENT_SERVER_COMMAND": str(plan.python_command),
        "ZCODE_AGENT_SERVER_ARGS_JSON": args_json,
        "ZCODE_KEYSMITH_SYSTEM_FILE": str(plan.paths.system_file),
        "ZCODE_KEYSMITH_ORIGINAL": str(plan.zcode_runtime),
        "ZCODE_KEYSMITH_NODE_COMMAND": str(plan.node_command),
        "ZCODE_KEYSMITH_CACHE_DIR": str(plan.paths.cache_dir),
        "ZCODE_KEYSMITH_LOG_DIR": str(plan.paths.log_dir),
    }


def render_config(plan: InstallPlan) -> str:
    payload = {
        "platform": "windows",
        "mode": "zcode-app-wrapper",
        "system_file": str(plan.paths.system_file),
        "wrapper": str(plan.paths.wrapper),
        "python_command": str(plan.python_command),
        "zcode_runtime": str(plan.zcode_runtime),
        "node_command": str(plan.node_command),
        "cache_dir": str(plan.paths.cache_dir),
        "wrapper_log": str(plan.paths.wrapper_log),
        "agent_server_args_json": env_values(plan)["ZCODE_AGENT_SERVER_ARGS_JSON"],
        "app_bundle_modified": False,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_wrapper(plan: InstallPlan) -> str:
    runtime_json = json.dumps(str(plan.zcode_runtime), ensure_ascii=False)
    system_file_json = json.dumps(str(plan.paths.system_file), ensure_ascii=False)
    node_command_json = json.dumps(str(plan.node_command), ensure_ascii=False)
    cache_dir_json = json.dumps(str(plan.paths.cache_dir), ensure_ascii=False)
    log_dir_json = json.dumps(str(plan.paths.log_dir), ensure_ascii=False)
    patch_needle_json = json.dumps(PATCH_NEEDLE, ensure_ascii=False)
    return f'''#!/usr/bin/env python3
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import threading

ORIGINAL_RUNTIME = pathlib.Path(os.environ.get("ZCODE_KEYSMITH_ORIGINAL") or {runtime_json})
SYSTEM_FILE = pathlib.Path(os.environ.get("ZCODE_KEYSMITH_SYSTEM_FILE") or {system_file_json})
NODE_COMMAND = os.environ.get("ZCODE_KEYSMITH_NODE_COMMAND") or {node_command_json}
PATCH_NEEDLE = {patch_needle_json}
CACHE_DIR = pathlib.Path(os.environ.get("ZCODE_KEYSMITH_CACHE_DIR") or {cache_dir_json})
LOG_DIR = pathlib.Path(os.environ.get("ZCODE_KEYSMITH_LOG_DIR") or {log_dir_json})
LOG_FILE = LOG_DIR / "wrapper-start.jsonl"


def system_prompt_expression() -> str:
    system_file = json.dumps(str(SYSTEM_FILE), ensure_ascii=False)
    return (
        "(this.config.systemPrompt&&this.config.systemPrompt.trim()?this.config.systemPrompt:"
        "(()=>{{try{{let e=process.env.ZCODE_KEYSMITH_SYSTEM_FILE||"
        + system_file
        + ";let t=require(\\\"node:fs\\\");return t.existsSync(e)?t.readFileSync(e,\\\"utf8\\\"):void 0}}catch{{return void 0}}}})())"
    )


def patched_runtime_path() -> pathlib.Path:
    original = ORIGINAL_RUNTIME.read_text(encoding="utf-8")
    if PATCH_NEEDLE not in original:
        raise RuntimeError(f"ZCode runtime patch anchor not found: {{ORIGINAL_RUNTIME}}")
    replacement = "customSystemPrompt:" + system_prompt_expression() + ",language:"
    patched = original.replace(PATCH_NEEDLE, replacement, 1)
    digest = hashlib.sha256((str(ORIGINAL_RUNTIME) + "\\0" + original + "\\0" + replacement).encode("utf-8")).hexdigest()[:16]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"zcode-keysmith-runtime-{{digest}}.cjs"
    if not path.exists() or path.read_text(encoding="utf-8", errors="ignore") != patched:
        tmp = path.with_name(f".{{path.name}}.tmp")
        tmp.write_text(patched, encoding="utf-8")
        tmp.replace(path)
    return path


def log_invocation(runtime: pathlib.Path, args: list[str]) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        event = {{
            "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "pid": os.getpid(),
            "argv": sys.argv,
            "agent_args": args,
            "runtime": str(runtime),
            "original_runtime": str(ORIGINAL_RUNTIME),
            "system_file": str(SYSTEM_FILE),
            "node_command": NODE_COMMAND,
        }}
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\\n")
    except Exception:
        pass


def _pump(src, dst, close_on_eof: bool) -> None:
    try:
        fd = src.fileno()
    except Exception:
        fd = None
    try:
        while True:
            if fd is not None:
                chunk = os.read(fd, 65536)
            else:
                chunk = src.read(1)
            if not chunk:
                break
            dst.write(chunk)
            dst.flush()
    except Exception:
        pass
    finally:
        if close_on_eof:
            try:
                dst.close()
            except Exception:
                pass


def main() -> int:
    runtime = patched_runtime_path()
    args = sys.argv[1:] or ["app-server", "--stdio"]
    log_invocation(runtime, args)
    env = os.environ.copy()
    env["ELECTRON_RUN_AS_NODE"] = "1"
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            [NODE_COMMAND, str(runtime), *args],
            env=env,
            creationflags=creationflags,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        threading.Thread(target=_pump, args=(sys.stdin.buffer, proc.stdin, True), daemon=True).start()
        threading.Thread(target=_pump, args=(proc.stdout, sys.stdout.buffer, False), daemon=True).start()
        threading.Thread(target=_pump, args=(proc.stderr, sys.stderr.buffer, False), daemon=True).start()
        return proc.wait()
    except KeyboardInterrupt:
        try:
            proc.terminate()
        except Exception:
            pass
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
'''


def read_user_env_var(name: str) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ENV_KEY) as key:
            value, _ = winreg.QueryValueEx(key, name)
        return str(value)
    except OSError:
        return None


def set_user_env_var(name: str, value: str) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, ENV_KEY, access=winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def delete_user_env_var(name: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ENV_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
        return True
    except FileNotFoundError:
        return False


def backup_user_env(plan: InstallPlan, values: dict[str, str] | None) -> Path:
    plan.paths.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = plan.paths.backup_dir / f"env-backup-{stamp}.json"
    previous = {name: read_user_env_var(name) for name in DEFAULT_ENV_VARS if read_user_env_var(name) is not None}
    payload = {"previous": previous, "installed": values or {}}
    atomic_write_text(backup, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return backup


def broadcast_env_change() -> None:
    try:
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, None
        )
    except Exception:
        pass


def activate_current_session(plan: InstallPlan) -> list[str]:
    results: list[str] = []
    values = env_values(plan)
    backup = backup_user_env(plan, values)
    results.append(f"user env backup: {backup}")
    for name, value in values.items():
        set_user_env_var(name, value)
        results.append(f"HKCU\\Environment {name}: set")
    broadcast_env_change()
    results.append("WM_SETTINGCHANGE: broadcast")
    return results


def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def install_lines(plan: InstallPlan, dry_run: bool, backups: list[Path], activation: list[str]) -> list[str]:
    values = env_values(plan)
    lines = ["zcode-keysmith (windows) install preview" if dry_run else "zcode-keysmith (windows) install complete"]
    lines.extend(
        [
            f"source_system_file: {plan.source_system_file}",
            f"system_file: {plan.paths.system_file}",
            f"config_file: {plan.paths.config_file}",
            f"wrapper: {plan.paths.wrapper}",
            f"zcode_runtime: {plan.zcode_runtime}",
            f"node_command: {plan.node_command}",
            f"python_command: {plan.python_command}",
            f"cache_dir: {plan.paths.cache_dir}",
            f"wrapper_log: {plan.paths.wrapper_log}",
            f"agent_server_args_json: {values['ZCODE_AGENT_SERVER_ARGS_JSON']}",
            "persistence: HKCU\\Environment (user env vars)",
            "app_bundle_modified: false",
            "api_key: not read or stored",
            f"zcode_running: {str(is_zcode_running()).lower()}",
            "activation_note: reopen ZCode and start a fresh task",
            f"write: {str(not dry_run).lower()}",
        ]
    )
    if dry_run:
        lines.append("tip: rerun with install --yes to write these files")
    for backup in backups:
        lines.append(f"backup: {backup}")
    lines.extend(activation)
    if not dry_run:
        lines.append("effect: new ZCode agent-server processes will use the managed wrapper")
    return lines


def runtime_node_from_args(args: argparse.Namespace) -> tuple[Path, Path]:
    explicit_app = getattr(args, "zcode_app", None)
    if explicit_app:
        return resolve_bundle_paths(expand_path(explicit_app))
    if os.environ.get("ZCODE_APP_PATH"):
        return resolve_bundle_paths(expand_path(os.environ["ZCODE_APP_PATH"]))
    runtime = expand_path(args.zcode_runtime)
    node_command = expand_path(args.node_command)
    if node_command.name.lower() == "zcode.exe" and runtime.name == "zcode.cjs":
        app = runtime.parent.parent.parent
        if (app / "ZCode.exe").exists():
            return resolve_bundle_paths(app)
    return runtime, node_command


def build_install_plan(args: argparse.Namespace) -> InstallPlan:
    paths = build_paths(expand_path(args.managed_dir))
    source_system_file = expand_path(args.system_file)
    zcode_runtime, node_command = runtime_node_from_args(args)
    python_command = expand_path(sys.executable)
    return InstallPlan(
        paths=paths,
        source_system_file=source_system_file,
        zcode_runtime=zcode_runtime,
        node_command=node_command,
        python_command=python_command,
        activate=not args.no_activate,
    )


def install(plan: InstallPlan, yes: bool, dry_run_flag: bool) -> list[str]:
    system_prompt = read_system_prompt_source(plan.source_system_file)
    ensure_runtime_patchable(plan.zcode_runtime)
    if not plan.node_command.exists():
        fallback = shutil.which(str(plan.node_command))
        if fallback:
            object.__setattr__(plan, "node_command", Path(fallback))  # type: ignore[misc]
        else:
            raise KeysmithError(f"node command not found: {plan.node_command}")
    if not plan.python_command.exists():
        raise KeysmithError(f"python command not found: {plan.python_command}")

    dry_run = dry_run_flag or not yes
    if dry_run:
        return install_lines(plan, dry_run=True, backups=[], activation=[])

    for directory in (plan.paths.managed_dir, plan.paths.wrapper.parent, plan.paths.log_dir, plan.paths.cache_dir):
        directory.mkdir(parents=True, exist_ok=True)

    write_targets = [
        plan.paths.system_file,
        plan.paths.config_file,
        plan.paths.wrapper,
    ]
    backups = [backup for target in write_targets if (backup := backup_existing(target))]

    atomic_write_text(plan.paths.system_file, system_prompt)
    atomic_write_text(plan.paths.config_file, render_config(plan))
    atomic_write_text(plan.paths.wrapper, render_wrapper(plan))

    activation = activate_current_session(plan) if plan.activate else []
    return install_lines(plan, dry_run=False, backups=backups, activation=activation)


def doctor_lines(paths: InstallPaths, zcode_runtime: Path, node_command: Path, python_command: Path) -> list[str]:
    prompt_hash = file_sha256(paths.system_file)
    runtime_patchable = False
    if zcode_runtime.exists() and zcode_runtime.is_file():
        try:
            runtime_patchable = PATCH_NEEDLE in zcode_runtime.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            runtime_patchable = False
    plan = InstallPlan(
        paths=paths,
        source_system_file=paths.system_file,
        zcode_runtime=zcode_runtime,
        node_command=node_command,
        python_command=python_command,
        activate=False,
    )
    expected_env = env_values(plan)
    lines = [
        "zcode-keysmith (windows) doctor",
        f"managed_dir: {paths.managed_dir}",
        f"system_file: {paths.system_file}",
        f"system_file_exists: {str(paths.system_file.exists()).lower()}",
        f"system_file_sha256: {prompt_hash or 'missing'}",
        f"config_file: {paths.config_file}",
        f"config_file_exists: {str(paths.config_file.exists()).lower()}",
        f"wrapper: {paths.wrapper}",
        f"wrapper_exists: {str(paths.wrapper.exists()).lower()}",
        f"zcode_runtime: {zcode_runtime}",
        f"zcode_runtime_exists: {str(zcode_runtime.exists()).lower()}",
        f"zcode_runtime_patchable: {str(runtime_patchable).lower()}",
        f"node_command: {node_command}",
        f"node_command_exists: {str(node_command.exists()).lower()}",
        f"python_command: {python_command}",
        f"python_command_exists: {str(python_command.exists()).lower()}",
        "persistence: HKCU\\Environment",
        "app_bundle_modified: false",
        "api_key: not read or stored",
    ]
    for key, expected in expected_env.items():
        current = read_user_env_var(key)
        lines.append(f"env.{key}: {'matches' if current == expected else 'not set' if not current else 'different'}")
    return lines


def is_agent_server_invocation(event: dict[str, object]) -> bool:
    args = event.get("agent_args")
    return isinstance(args, list) and len(args) >= 2 and args[0] == "app-server" and args[1] == "--stdio"


def read_last_wrapper_invocation(paths: InstallPaths) -> dict[str, object] | None:
    if not paths.wrapper_log.exists() or not paths.wrapper_log.is_file():
        return None
    try:
        lines = [line.strip() for line in paths.wrapper_log.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    except OSError:
        return None
    for line in reversed(lines):
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict) and is_agent_server_invocation(loaded):
            return loaded
    return None


def run_wrapper_smoke(paths: InstallPaths, python_command: Path, timeout: float = 20.0) -> tuple[bool, str]:
    if not paths.wrapper.exists():
        return False, "wrapper missing"
    completed = subprocess.run(
        [str(python_command), str(paths.wrapper), "--help"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode == 0:
        return True, "ok"
    detail = (completed.stderr or completed.stdout).strip().splitlines()
    return False, detail[0] if detail else f"exit {completed.returncode}"


def verify_lines(paths: InstallPaths, zcode_runtime: Path, node_command: Path, python_command: Path, smoke: bool = True) -> list[str]:
    prompt_hash = file_sha256(paths.system_file)
    zcode_app = None
    if zcode_runtime.exists():
        for parent in zcode_runtime.parents:
            if parent.name.lower().endswith(".app") or (parent / "ZCode.exe").exists():
                zcode_app = parent
                break
    runtime_patchable = False
    if zcode_runtime.exists() and zcode_runtime.is_file():
        try:
            runtime_patchable = PATCH_NEEDLE in zcode_runtime.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            runtime_patchable = False
    smoke_ok, smoke_detail = run_wrapper_smoke(paths, python_command) if smoke else (False, "skipped")
    last_invocation = read_last_wrapper_invocation(paths)
    wrapper_invoked = last_invocation is not None
    lines = [
        "zcode-keysmith (windows) verify",
        f"system_file_exists: {str(paths.system_file.exists()).lower()}",
        f"system_file_sha256: {prompt_hash or 'missing'}",
        f"wrapper_exists: {str(paths.wrapper.exists()).lower()}",
        f"wrapper_smoke: {str(smoke_ok).lower()}",
        f"wrapper_smoke_detail: {smoke_detail}",
        f"wrapper_log: {paths.wrapper_log}",
        f"wrapper_invoked: {str(wrapper_invoked).lower()}",
        f"last_wrapper_start: {last_invocation.get('started_at') if last_invocation else 'missing'}",
        f"zcode_app: {zcode_app or 'unknown'}",
        f"zcode_agent_override_supported: {str(app_supports_agent_server_override(zcode_app)).lower()}",
        f"zcode_runtime_exists: {str(zcode_runtime.exists()).lower()}",
        f"zcode_runtime_patchable: {str(runtime_patchable).lower()}",
        f"node_command_exists: {str(node_command.exists()).lower()}",
        f"zcode_running: {str(is_zcode_running()).lower()}",
        "api_key: not read or stored",
    ]
    if is_zcode_running():
        lines.append("activation_note: reopen ZCode and start a fresh task")
    return lines


def uninstall_lines(paths: InstallPaths, dry_run: bool, backups: list[Path], removed_env: list[str]) -> list[str]:
    lines = ["zcode-keysmith (windows) uninstall preview" if dry_run else "zcode-keysmith (windows) uninstall complete"]
    for path in [paths.system_file, paths.config_file, paths.wrapper]:
        lines.append(f"target: {path}")
    lines.append("target: HKCU\\Environment (keysmith env vars)")
    lines.append(f"write: {str(not dry_run).lower()}")
    for backup in backups:
        lines.append(f"backup: {backup}")
    for name in removed_env:
        lines.append(f"env removed: {name}")
    return lines


def uninstall(paths: InstallPaths, yes: bool, dry_run_flag: bool, activate: bool) -> list[str]:
    dry_run = dry_run_flag or not yes
    if dry_run:
        return uninstall_lines(paths, dry_run=True, backups=[], removed_env=[])
    backups = []
    for path in [paths.system_file, paths.config_file, paths.wrapper]:
        if path.exists():
            backup = backup_existing(path)
            if backup:
                backups.append(backup)
    removed_env = []
    if activate:
        values = {name: read_user_env_var(name) for name in DEFAULT_ENV_VARS if read_user_env_var(name) is not None}
        backup = backup_user_env(paths, None)
        backups.append(backup)
        for name in DEFAULT_ENV_VARS:
            if delete_user_env_var(name):
                removed_env.append(name)
        broadcast_env_change()
    return uninstall_lines(paths, dry_run=False, backups=backups, removed_env=removed_env)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install or inspect zcode-keysmith managed ZCode App system-role entrypoint (Windows port)."
    )
    sub = parser.add_subparsers(dest="command")

    install_parser = sub.add_parser("install", help="Install managed ZCode App wrapper and system-role file")
    install_parser.add_argument("--system-file", default=str(DEFAULT_SOURCE_SYSTEM_FILE), help="Source Markdown system prompt. Default: examples/system-role.md")
    install_parser.add_argument("--managed-dir", default=str(DEFAULT_MANAGED_DIR), help="Managed install directory. Default: ~/.zcode-keysmith")
    install_parser.add_argument("--zcode-app", default=None, help="ZCode install directory. When provided, runtime and node command are derived from it")
    install_parser.add_argument("--zcode-runtime", default=str(DEFAULT_ZCODE_APP / "resources" / "glm" / "zcode.cjs"), help="Bundled ZCode runtime file")
    install_parser.add_argument("--node-command", default=str(DEFAULT_ZCODE_APP / "ZCode.exe"), help="Command used to run the patched runtime")
    install_parser.add_argument("--dry-run", action="store_true", help="Preview paths and checks without writing")
    install_parser.add_argument("--yes", action="store_true", help="Allow writing files. --dry-run wins if both are provided")
    install_parser.add_argument("--no-activate", action="store_true", help="Write files without updating HKCU\\Environment user env vars")

    doctor_parser = sub.add_parser("doctor", help="Inspect managed install state")
    doctor_parser.add_argument("--managed-dir", default=str(DEFAULT_MANAGED_DIR))
    doctor_parser.add_argument("--zcode-app", default=None)
    doctor_parser.add_argument("--zcode-runtime", default=str(DEFAULT_ZCODE_APP / "resources" / "glm" / "zcode.cjs"))
    doctor_parser.add_argument("--node-command", default=str(DEFAULT_ZCODE_APP / "ZCode.exe"))

    verify_parser = sub.add_parser("verify", help="Run local wrapper/runtime verification without sending model requests")
    verify_parser.add_argument("--managed-dir", default=str(DEFAULT_MANAGED_DIR))
    verify_parser.add_argument("--zcode-app", default=None)
    verify_parser.add_argument("--zcode-runtime", default=str(DEFAULT_ZCODE_APP / "resources" / "glm" / "zcode.cjs"))
    verify_parser.add_argument("--node-command", default=str(DEFAULT_ZCODE_APP / "ZCode.exe"))
    verify_parser.add_argument("--no-smoke", action="store_true", help="Skip local wrapper --help smoke test")

    uninstall_parser = sub.add_parser("uninstall", help="Back up managed files and remove user env vars")
    uninstall_parser.add_argument("--managed-dir", default=str(DEFAULT_MANAGED_DIR))
    uninstall_parser.add_argument("--dry-run", action="store_true")
    uninstall_parser.add_argument("--yes", action="store_true")
    uninstall_parser.add_argument("--no-activate", action="store_true")

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        command = args.command or "doctor"
        if command == "install":
            plan = build_install_plan(args)
            print("\n".join(install(plan, yes=args.yes, dry_run_flag=args.dry_run)))
            return 0
        if command == "doctor":
            paths = build_paths(expand_path(args.managed_dir))
            zcode_runtime, node_command = runtime_node_from_args(args)
            print("\n".join(doctor_lines(paths, zcode_runtime, node_command, expand_path(sys.executable))))
            return 0
        if command == "verify":
            paths = build_paths(expand_path(args.managed_dir))
            zcode_runtime, node_command = runtime_node_from_args(args)
            print("\n".join(verify_lines(paths, zcode_runtime, node_command, expand_path(sys.executable), smoke=not args.no_smoke)))
            return 0
        if command == "uninstall":
            paths = build_paths(expand_path(args.managed_dir))
            print("\n".join(uninstall(paths, yes=args.yes, dry_run_flag=args.dry_run, activate=not args.no_activate)))
            return 0
        parser.print_help()
        return 1
    except KeysmithError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

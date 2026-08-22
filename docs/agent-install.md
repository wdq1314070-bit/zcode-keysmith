<!-- markdownlint-disable MD013 -->

# 复制给智能体安装（Windows 版）/ Copy this to an agent (Windows)

把下面这段话复制给 Codex、Claude Code、Cursor Agent、ChatGPT Agent 或其他本地智能体。执行流程只有一次确认：确认是否写入持久化入口文件。

本仓库为 [Jia-Ethan/zcode-keysmith](https://github.com/Jia-Ethan/zcode-keysmith) 的 fork。Windows 支持自上游 `v0.1.1` 起已并入统一脚本 `zcode-keysmith.py`（Windows 用 `py` 运行，不需要管理员权限）；本 fork 另保留早期移植的 `zcode-keysmith-win.py` 作为备用。

## Windows 版提示词（中文）

```text
请使用 https://github.com/wdq1314070-bit/zcode-keysmith 帮我在 Windows 上安装 ZCode App 的 managed true system-role entrypoint。

执行要求：
1. 先阅读 README.md 和 zcode-keysmith.py。
2. 运行：py zcode-keysmith.py install --dry-run（如果没有 py 启动器，改用 python zcode-keysmith.py）。
3. 向我展示将写入的准确路径，必须包括：
   - ~/.zcode-keysmith/system-role.md
   - ~/.zcode-keysmith/config.json
   - ~/.zcode-keysmith/bin/zcode-agent-wrapper.py
   - ~/.zcode-keysmith/bin/zcode-keysmith-env.ps1 和 HKCU\Environment 的 ZCODE_* 值
   说明：Windows 版没有 LaunchAgent plist；入口写入当前用户环境变量，不需要管理员权限。
4. 同时展示将使用的 ZCode runtime 路径、ZCode node command 路径（ZCode.exe）、python 命令路径、agent-server args，以及 app_bundle_modified: false。
5. API key、token、MCP 配置、ZCode provider 配置由 ZCode 自身管理；安装器不读取、不保存、不打印这些内容。
6. 只问我一次：是否确认写入以上持久化入口文件。
7. 我确认后，运行：py zcode-keysmith.py install --yes。
8. 写入后运行：py zcode-keysmith.py doctor。
9. 再运行：py zcode-keysmith.py verify。
10. 提醒我完全退出并重新打开 ZCode，然后新建任务测试"你是谁"。测试后再次运行 verify，确认 wrapper_invoked: true。
```

## Windows 版提示词（English）

```text
Use https://github.com/wdq1314070-bit/zcode-keysmith to install the managed true system-role entrypoint for my local ZCode App (Windows).

Requirements:
1. Read README.md and zcode-keysmith.py first.
2. Run: py zcode-keysmith.py install --dry-run (fall back to python zcode-keysmith.py if the py launcher is missing).
3. Show the exact write targets:
   - ~/.zcode-keysmith/system-role.md
   - ~/.zcode-keysmith/config.json
   - ~/.zcode-keysmith/bin/zcode-agent-wrapper.py
   - ~/.zcode-keysmith/bin/zcode-keysmith-env.ps1 and the ZCODE_* values under HKCU\Environment
   Note: the Windows port has no LaunchAgent plist; the entrypoint goes into current-user environment values and needs no administrator access.
4. Also show the ZCode runtime path, ZCode node command path (ZCode.exe), python command path, agent-server args, and app_bundle_modified: false.
5. API keys, tokens, MCP config, and provider config stay managed by ZCode. The installer must not read, store, or print them.
6. Ask once whether to write the managed entrypoint files.
7. After confirmation, run: py zcode-keysmith.py install --yes.
8. Then run: py zcode-keysmith.py doctor.
9. Then run: py zcode-keysmith.py verify.
10. Tell me to fully quit and reopen ZCode, then test a fresh task with "Who are you?". After the test, run verify again and confirm wrapper_invoked: true.
```

<!-- markdownlint-disable MD013 -->

# 复制给智能体安装（Windows 版）/ Copy this to an agent (Windows)

把下面这段话复制给 Codex、Claude Code、Cursor Agent、ChatGPT Agent 或其他本地智能体。执行流程只有一次确认：确认是否写入持久化入口文件。

本仓库为 [Jia-Ethan/zcode-keysmith](https://github.com/Jia-Ethan/zcode-keysmith) 的 Windows 增强 fork，Windows 安装使用 `zcode-keysmith-win.py`（macOS 版逻辑的 Windows 移植，含 stdio 管道修复）。

> [!TIP]
> 需要安装 macOS 版时改回上游仓库与 `zcode-keysmith.py`,见上游 <https://github.com/Jia-Ethan/zcode-keysmith>。

## Windows 版提示词（中文）

```text
请使用 https://github.com/wdq1314070-bit/zcode-keysmith 帮我在 Windows 上安装 ZCode App 的 managed true system-role entrypoint（Windows 版）。

执行要求：
1. 先阅读 README.md 和 zcode-keysmith-win.py。
2. 运行：python3 zcode-keysmith-win.py install --dry-run。
3. 向我展示将写入的准确路径，必须包括：
   - ~/.zcode-keysmith/system-role.md
   - ~/.zcode-keysmith/config.json
   - ~/.zcode-keysmith/bin/zcode-agent-wrapper.py
   说明：Windows 版没有 zcode-keysmith-env.sh 和 LaunchAgent plist；持久化走 HKCU\Environment 用户环境变量。
4. 同时展示将使用的 ZCode runtime 路径、ZCode node command 路径（ZCode.exe）、python 命令路径、agent-server args，以及 app_bundle_modified: false。
5. API key、token、MCP 配置、ZCode provider 配置由 ZCode 自身管理；安装器不读取、不保存、不打印这些内容。
6. 只问我一次：是否确认写入以上持久化入口文件。
7. 我确认后，运行：python3 zcode-keysmith-win.py install --yes。
8. 写入后运行：python3 zcode-keysmith-win.py doctor。
9. 再运行：python3 zcode-keysmith-win.py verify。
10. 提醒我完全退出并重新打开 ZCode，然后新建任务测试"你是谁"。测试后再次运行 verify，确认 wrapper_invoked: true。
```

## Windows 版提示词（English）

```text
Use https://github.com/wdq1314070-bit/zcode-keysmith to install the managed true system-role entrypoint for my local ZCode App (Windows).

Requirements:
1. Read README.md and zcode-keysmith-win.py first.
2. Run: python3 zcode-keysmith-win.py install --dry-run.
3. Show the exact write targets:
   - ~/.zcode-keysmith/system-role.md
   - ~/.zcode-keysmith/config.json
   - ~/.zcode-keysmith/bin/zcode-agent-wrapper.py
   Note: the Windows port has no zcode-keysmith-env.sh and no LaunchAgent plist; persistence uses HKCU\Environment user environment variables.
4. Also show the ZCode runtime path, ZCode node command path (ZCode.exe), python command path, agent-server args, and app_bundle_modified: false.
5. API keys, tokens, MCP config, and provider config stay managed by ZCode. The installer must not read, store, or print them.
6. Ask once whether to write the managed entrypoint files.
7. After confirmation, run: python3 zcode-keysmith-win.py install --yes.
8. Then run: python3 zcode-keysmith-win.py doctor.
9. Then run: python3 zcode-keysmith-win.py verify.
10. Tell me to fully quit and reopen ZCode, then test a fresh task with "Who are you?". After the test, run verify again and confirm wrapper_invoked: true.
```

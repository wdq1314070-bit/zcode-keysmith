# ZCode + keysmith Windows 兼容性修复报告

**日期：** 2026-08-15
**环境：** Windows / ZCode 桌面版 3.7.7（Electron 41.0.3，agent 0.16.3） / keysmith 补丁工具
**用户名含中文：** `yolo.白鹿 唐陆凤`

---

## 一、问题现象

1. 打开 ZCode 桌面版后，agent 启动即退出，界面报 **"ZCode agent transport closed"**。
2. 修复第一问题后，发送消息时**发送按钮一直转圈**（agent 对请求 180 秒无响应后超时）。

## 二、背景

用户安装了 keysmith 工具，用于给 ZCode 注入自定义 system prompt（在 Mac 上正常，Windows 上异常）。
keysmith 通过设置 **用户级环境变量** 强制 ZCode 桌面版用 Python 包装脚本启动 agent：

- `ZCODE_AGENT_SERVER_COMMAND = python.exe`
- `ZCODE_AGENT_SERVER_ARGS_JSON = ["...\.zcode-keysmith\bin\zcode-agent-wrapper.py","app-server","--stdio"]`
- 以及 `ZCODE_KEYSMITH_*` 系列变量

桌面版 → `python.exe zcode-agent-wrapper.py app-server --stdio` → `ZCode.exe`（`ELECTRON_RUN_AS_NODE=1`）→ patched runtime `zcode.cjs`。

## 三、根因分析

### 问题 1：`ZCode agent transport closed`

- 原包装脚本用 `subprocess.run([...])` **继承 stdio 句柄**启动 agent。
- Windows 上，桌面端（node/Electron）用管道建立的 stdio 经 Python 中转后句柄继承不稳定，agent 启动约 **1.5 秒**即自行退出（exit code 0），桌面端判定 transport closed。
- Mac 上 POSIX 管道继承正常，故无此问题。

### 问题 2：发送按钮一直转圈（请求 180s 超时）

- 修复问题 1 后改用 `subprocess.Popen` + 显式中继线程转发 stdio。
- 但中继线程使用 `src.read(65536)`（`BufferedReader.read(n)`）转发数据。**Windows 管道上 `BufferedReader.read(n)` 会阻塞到读满 n 字节或 EOF 才返回**，而桌面端请求仅几百字节，永远凑不齐，请求被卡在中继缓冲区里无法送达 agent。
- 直到 180 秒后桌面端超时关闭 stdin（EOF），缓冲区的请求才一次性冲出——与 agent 日志中"启动完成 180 秒后才突然处理 provider registry"完全吻合。

## 四、修复方案

修改 `~/.zcode-keysmith/bin/zcode-agent-wrapper.py`（keysmith 逻辑全部保留）：

1. `subprocess.run` 改为 `subprocess.Popen`，stdin/stdout/stderr 全部显式 `PIPE`。
2. 三个中继线程转发数据，**读取改用 `os.read(fd, 65536)`**——Windows 管道上一有数据立即返回部分数据，解决阻塞问题。
3. 父进程 stdin EOF 时关闭 agent stdin（保证退出行为与桌面端预期一致）。
4. 退出码与 agent 返回码一致；`KeyboardInterrupt` 时终止子进程返回 130。

保留原有：patched runtime 的 sha256 缓存逻辑、自定义 system prompt 注入表达式、启动日志 `wrapper-start.jsonl`、`ELECTRON_RUN_AS_NODE=1`、`CREATE_NO_WINDOW`。

## 五、验证结果

| 场景 | 修改前 | 修改后 |
| --- | --- | --- |
| agent 存活 | 约 1.5s 退出 | 持续存活，直到 stdin 关闭 |
| 请求→响应延迟 | 无响应 / 180s 后 EOF 冲刷 | **6ms 内响应**（实测 2007ms 发送，2013ms 收到） |
| 双向管道 | 失败 | 正常 |

agent 日志确认：启动 99ms 完成，provider registry 同步正常。

## 六、相关文件

| 文件 | 说明 |
| --- | --- |
| `~/.zcode-keysmith/bin/zcode-agent-wrapper.py` | 修复后的包装脚本 |
| `~/.zcode-keysmith/bin/zcode-agent-wrapper.py.bak-20260815_135816` | 修复前备份 |
| `~/.zcode-keysmith/cache/zcode-keysmith-runtime-4afd29db2989896c.cjs` | patched runtime 缓存 |
| `D:\ZCode\resources\glm\zcode.cjs` | 原始 runtime |
| `~/.zcode\cli\config.json` | 注意：`chrome-mcp-server.type` 为 `streamableHttp`（应为 `stdio`/`http`/`sse`），该 MCP 服务器被跳过，仅为警告，不影响使用 |

## 七、keysmith 更新后的修复流程

keysmith 自动更新可能覆盖 `zcode-agent-wrapper.py`，导致问题复发。复现时的修复步骤：

1. **检查是否复发：** 打开 ZCode，看是否报 transport closed / 发送转圈。
2. **对比文件：** `diff` 当前文件与 `zcode-agent-wrapper.py.bak-20260815_135816`。若文件被更新覆盖，需重新应用修复。
3. **重新应用修复：** 将 `main()` 中的 `subprocess.run(...)` 替换为 `Popen` + `os.read` 中继模式（见上文第四节 / 可对照当前已修复文件）。

```python
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
```

4. **验证：** 用 node 脚本模拟桌面端 spawn（管道发消息），确认请求发出后 agent 立即响应。
5. **重启 ZCode**（托盘图标完全退出）验证。

> 提示：我无法主动监测 keysmith 的更新；keysmith 更新后如发现问题，把报错/日志发给我，我按此报告快速重新修复。
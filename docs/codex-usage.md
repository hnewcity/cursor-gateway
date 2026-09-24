# Codex CLI 接入指南

**简体中文** · [English](en/codex-usage.md)

[← 返回 README](../README.md) · [API 参考](api-reference.md)

以下命令在仓库根目录执行，需要先按 README 启动网关。示例模型应替换为 `/v1/models` 中当前账号可用的模型。

本地安装 `codex` 后，用启动器接入网关：

```bash
# 交互式使用；保留日常 Codex 配置与客户端的权限设置。
.venv/bin/python scripts/run_codex.py --model grok-4.6-medium

# 独立测试配置。
.venv/bin/python scripts/run_codex.py --model grok-4.6-medium -- \
  exec --ignore-user-config --sandbox workspace-write \
  '创建一个 hello.py，运行并检查输出'

# 恢复指定 Codex 会话；SESSION_ID 来自 Codex。
.venv/bin/python scripts/run_codex.py --model grok-4.6-medium -- \
  exec resume --ignore-user-config SESSION_ID '继续刚才的任务'
```

`--url` 可指定其他网关地址。配置了网关 API key 时，先在当前终端导出
`CURSOR_DIRECT_API_KEY`。启动器生成临时模型目录，使用 Responses HTTP/SSE，
启用 Cursor 原生搜索，并把配置放到 `exec` / `resume` / `review` 的正确位置；
不修改 `~/.codex/config.toml`。启动提示写到 stderr，`exec --json` 的 stdout 保持 JSONL。

默认客户端上下文预算为 65,536 tokens，可用 `--context-window` 调整；
这是客户端预算，不是对所有 Cursor 模型原生窗口大小的承诺。模型不支持视觉时使用
`--text-only`。指定图片的 `--image` 后应以 `--` 分隔提示词，避免 CLI 将提示词当成图片路径。

工具由 Codex 客户端执行，包含 MCP 的审批规则与沙箱仍由客户端控制。
默认保留等待客户端工具结果的 Cursor Run；后续 Responses 请求的历史、指令、工具定义
和完整工具结果批次一致时，直接把结果交回同一条上游流，保留原生推理和工作进度。
这也适用于 Codex 常用的 `store=false`，不依赖 `previous_response_id`。
工具等待默认最多 300 秒、最多保留 8 个 Run；结束、取消、过期或服务关闭会释放连接。
指令/工具变化、分支、压缩、重启或缓存淘汰后，使用完整历史回放，并保留近期推理摘要。
自定义 provider 的自动压缩可走 Codex 本地摘要流程；网关也实现独立的
`/v1/responses/compact` 和流内 `compaction_trigger`。

接口行为与限制见 [API 参考](api-reference.md)。开发和自动化验证方式见 [贡献指南](../CONTRIBUTING.md)。

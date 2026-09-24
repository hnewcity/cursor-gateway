# API 参考

**简体中文** · [English](en/api-reference.md)

[← 返回 README](../README.md) · [Codex 接入指南](codex-usage.md)

服务默认监听 `http://127.0.0.1:8790`，客户端 Base URL 为 `http://127.0.0.1:8790/v1`。
配置网关密钥后，所有 `/v1/*` 接口都需要 `Authorization: Bearer <key>` 或 `x-api-key`。
下方示例从终端环境读取 `CURSOR_DIRECT_API_KEY`；若只在服务端 `.env` 中设置了密钥，
请在运行示例的终端导出相同值。网关未配置密钥时，示例中的 `unused` 可以直接使用。

交互式接口文档位于 `/docs`，ReDoc 位于 `/redoc`，OpenAPI 描述位于 `/openapi.json`。

## Responses API

`POST /v1/responses` 使用 Responses 的 `input` 和扁平函数工具定义。
现有 `/v1/chat/completions` 可以继续使用。

```bash
curl http://127.0.0.1:8790/v1/responses \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","instructions":"请用中文简洁回答。","input":"解释一下 HTTP/2"}'

curl -N http://127.0.0.1:8790/v1/responses \
  -H "Authorization: Bearer ${CURSOR_DIRECT_API_KEY:-unused}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","input":"你好","stream":true,"store":false}'
```

返回对象的 `object` 为 `response`，文本位于
`output[].content[]` 的 `output_text` 项。上游 thinking 增量映射为 `reasoning`
输出项的 `summary_text`，不混入可见回答。

可直接使用官方 Python SDK（示例运行于 Python 3.14；SDK 已包含在开发依赖中）：

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8790/v1",
    api_key=os.getenv("CURSOR_DIRECT_API_KEY") or "unused",
)
# 使用 /v1/models 返回的模型名。
model = "auto"
response = client.responses.create(
    model=model,
    instructions="请用中文简洁回答。",
    input="HTTP/2 有哪些特点？",
)
print(response.output_text)

# 按 ID 续接；需要的 instructions 每轮重新提供。
followup = client.responses.create(
    model=model,
    previous_response_id=response.id,
    instructions="请用中文简洁回答。",
    input="再举一个例子。",
)
print(followup.output_text)

# stream=True 返回带类型的 Responses 事件。
stream = client.responses.create(model=model, input="你好", stream=True)
for event in stream:
    if event.type == "response.output_text.delta":
        print(event.delta, end="", flush=True)
    elif event.type == "response.failed":
        raise RuntimeError(event.response.error.message)
```

也支持 SDK 的 `client.responses.stream(...)` 上下文管理器及 `get_final_response()`。
SSE 包含递增的 `sequence_number` 和对应的 `event:` 名称：

- `response.created`、`response.in_progress`
- `response.output_item.added` / `.done`
- `response.content_part.added` / `.done`、`response.output_text.delta` / `.done`
- `response.reasoning_summary_part.added` / `.done`、`response.reasoning_summary_text.delta` / `.done`
- `response.function_call_arguments.delta` / `.done`
- `response.completed` 或 `response.failed`

终止事件包含完整响应和 usage；Responses 流不发送 Chat Completions 的 `[DONE]`。
首个输出前的上游错误保留 HTTP 状态，开始输出后的错误使用 `response.failed`。
工具调用作为已完成的响应交给调用方，响应状态为 `completed`。

Responses 工具调用示例（沿用上面的 `client` 和 `model`）：

```python
import json

tools = [{
    "type": "function",
    "name": "get_weather",
    "description": "查询城市天气",
    "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}]
response = client.responses.create(
    model=model, input="北京天气怎么样？", tools=tools,
)
tool_outputs = []
for item in response.output:
    if item.type == "function_call":
        args = json.loads(item.arguments)
        # 在调用方执行真实工具；这里仅提供演示数据。
        result = {"city": args["city"], "temperature": 25, "condition": "sunny"}
        tool_outputs.append({
            "type": "function_call_output",
            "call_id": item.call_id,
            "output": json.dumps(result, ensure_ascii=False),
        })
if tool_outputs:
    response = client.responses.create(
        model=model, previous_response_id=response.id, tools=tools, input=tool_outputs,
    )
print(response.output_text)
```

回传结果使用 `call_id`，而不是输出项的 `id`。也可以不使用响应 ID：
设置 `store=false`，在下一轮 `input` 中依次传入先前输入、`response.output` 和
`function_call_output`。直接回传 SDK 对象时，可用
`item.model_dump(exclude_none=True)` 转成字典。推理摘要可原样回传，网关不会将它当作回答正文。

历史管理接口均需要网关鉴权：

| 接口 | 用途 |
|---|---|
| `GET /v1/responses/{response_id}` | 查询已保存的完整 JSON 响应 |
| `DELETE /v1/responses/{response_id}` | 删除该响应及其输入快照 |
| `GET /v1/responses/{response_id}/input_items` | 查看续接所用的输入历史，支持 `after`、`limit`、`order` |

`store` 默认为 `true`。历史仅保存在当前进程内存中，默认保留 1 小时，
最多 256 条响应、序列化总量最多 128 MiB；容量不足时淘汰最近最少访问的响应。
有效期从保存时计算，读取不延长有效期，过期项在下次访问缓存时清理。
重启会清空缓存，多进程/多实例不共享历史；这类部署可使用 `store=false` 并自行携带完整历史。
缓存未命中返回 `404`，不会丢弃历史继续生成。删除父响应不会删除已保存子响应中的历史副本。
缓存作用域是整个网关，遵循同一个网关 API key 的访问权限。

`previous_response_id` 会恢复先前输入和输出；不沿用上次顶层 `instructions` 和工具定义。
本轮未指定 `model` 时沿用前一响应的模型。合并历史和最终响应各自受
`CURSOR_DIRECT_MAX_BODY_BYTES` 限制，Responses 流也会限制累计输出量。

当前 Responses 兼容范围：

- 支持 `type="namespace"` 下的 `function` / `custom` 工具；不同命名空间允许同名工具。
  返回的调用保留原始 `name` 和 `namespace`，函数参数与自定义文本输入均可通过
  JSON / SSE 返回，再使用 `function_call_output` / `custom_tool_call_output` 续接。
  工具仍由客户端执行，网关不执行客户端的 shell、补丁或文件操作。
- 接受 Codex 的 `include=["reasoning.encrypted_content"]`。
  Cursor 没有 OpenAI 的加密 reasoning 状态，因此不生成 `encrypted_content`；
  reasoning 摘要会保留在 Responses 历史中。`CURSOR_DIRECT_REPLAY_REASONING=true`
  默认将近期摘要作为历史助手工作记录传入 Cursor，供无法复用原生 Run 时恢复进度，
  总预算为 12,000 字符；超限时保留较新的记录，并标注截断。
  来自其他服务的已有加密 reasoning 仍无法解密，会返回 `400`。
- 助手消息在完成时标注 `phase="commentary"` 或 `phase="final_answer"`；
  流式客户端在 `response.output_item.done` 获取最终 phase，创建事件不猜测尚未知的阶段。
  回放时保留原始 phase，并在 Cursor 助手历史文本中附上阶段说明。
- `web_search` / `web_search_preview` 使用 Cursor 原生搜索，产生 `web_search_call`、
  搜索来源及对应 SSE 事件。Cursor 搜索使用的临时文档仅保存在原生 Run 的内存中，
  不读写网关主机或客户端的工作区。暂不支持 OpenAI 的地理位置或域名过滤选项。
- 自定义工具支持纯文本，以及作为模型提示的 lark/regex grammar；不保证 grammar 约束解码。
  网关校验自定义工具的 `input` 字符串，并对 Codex 补丁 grammar 做边界格式检查。
  首个外部工具调用发出前，格式错误会反馈到同一个 Cursor Run，默认允许 1 次修正；
  未修正则返回明确的工具输入错误。已发出部分调用的并行批次仍交客户端校验，
  避免丢失同批工具结果。网关不改写补丁，不执行文件操作。
  客户端继续负责完整语法及执行校验。`defer_loading` 工具按普通已加载工具处理。
- 图片支持 base64 data URL，可作为用户输入或工具结果；支持 PNG、JPEG、WebP、GIF。
  远程图片 URL、文件 ID、音频、其他托管内置工具、`item_reference` 返回 `400`。
- `tool_search` 支持客户端发现工具和结果续接；服务端声明的 deferred 工具按已加载处理。
- `text.format` 支持 `json_object` / `json_schema`：通过提示约束模型并校验最终答案。
  上游不提供原生约束解码；不合规输出返回错误，不冒充成功的 JSON。
- `/v1/responses/compact` 和流内 `compaction_trigger` 生成网关加密的摘要检查点，
  保留未完成工具调用和已发现工具。`compaction.key` 默认与账号文件同目录，
  应随账号目录持久化；同一 key 可在服务重启后继续解码。它与 OpenAI 加密 reasoning 无关。
- `background=true`、`conversation`、托管 `prompt`、自动截断、其他 `include` 字段和
  强制工具选择返回 `400`。Codex 的客户端压缩、工具执行和会话恢复不要求这些功能。
- `temperature`、`top_p`、`max_output_tokens`、`max_tool_calls`、`reasoning` 设置、
  `text.verbosity` 和工具 `strict` 可以传入，但上游没有已实现的控制字段或严格校验保证。
  `parallel_tool_calls=true` 时收集同批到达的多个 MCP 调用，由客户端执行；
  上游是否产生并行调用取决于模型。整数参数递归恢复为 JSON 整数，保留小数、字符串和布尔值。
- Responses 输入 token 是标有 `estimated=true` 的估算，用于客户端压缩预算；
  上游 token 计数映射为 `output_tokens`，缓存/reasoning 明细没有可靠的独立计数。
- 使用 HTTP/SSE，不实现 WebSocket 或后台响应管理接口；客户端断连会取消上游请求。
  这提供 Codex 的兼容接入，不等同于 OpenAI 全部托管 API 或模型原生能力。

协议对照：
[创建响应](https://developers.openai.com/api/reference/resources/responses/methods/create)、
[流式事件](https://developers.openai.com/api/reference/resources/responses/streaming-events)、
[函数工具](https://developers.openai.com/api/docs/guides/function-calling)。

## Chat Completions 工具调用

请求中的工具使用标准函数定义：

```json
{
  "model": "auto",
  "messages": [{"role": "user", "content": "北京天气怎么样？"}],
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "查询城市天气",
      "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"]
      }
    }
  }]
}
```

收到 `finish_reason: "tool_calls"` 后，由调用方执行工具，再把完整的 assistant 消息
和工具结果加入下一次请求的 `messages`：

```json
{
  "role": "tool",
  "tool_call_id": "使用上一步返回的调用 ID",
  "content": "{\"temperature\":25,\"condition\":\"sunny\"}"
}
```

Chat Completions 使用完整历史回放：网关将历史工具调用和结果重放给 Cursor，并发送继续回答的用户回合。
`parallel_tool_calls=true` 时可收集上游同批到达的多个调用；工具由调用方执行。
工具参数按 `google.protobuf.Value` 解码，支持对象、数组、布尔值、数字和 null。
上游调用 ID 中的换行等字符会转换为下划线，避免下游客户端拒绝该 ID。

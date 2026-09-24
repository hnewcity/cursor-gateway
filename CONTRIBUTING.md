# Contributing / 贡献指南

Thanks for helping improve Cursor Gateway. Small, focused pull requests are welcome.

## Development

Use Python 3.14 and run commands from the repository root:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check src scripts tests
.venv/bin/ruff format --check src scripts tests
.venv/bin/python -m build
```

The automated suite uses synthetic credentials and a local mock upstream. A Cursor account, paid quota,
and an installed Codex CLI are not required. Keep new tests deterministic and independent of personal configuration.
Use temporary directories for generated files.

## Pull requests

- Describe the problem, the changed behavior, and how you verified it.
- Add regression coverage for behavior changes. Documentation-only changes do not need new tests.
- Update both [Chinese](README.md) and [English](docs/en/README.md) documentation when changing user-facing behavior,
  examples, or configuration. Check links from each translated file's own directory.
- Keep commits focused. Do not include local experiments, conversation exports, account files, private endpoints,
  credentials, or test reports.
- Preserve upstream attribution and the AGPL-3.0-only license. Contributions are submitted under the project's license.

Use Issues for reproducible bugs and feature discussions. For vulnerabilities, follow [SECURITY.md](SECURITY.md).
Please follow the [code of conduct](CODE_OF_CONDUCT.md).

## 中文说明

请使用 Python 3.14，在仓库根目录执行上面的安装、测试和检查命令。自动化测试使用虚构凭据和本地模拟上游，
无需真实 Cursor 账号、付费额度或 Codex CLI。新增测试应使用临时目录，避免依赖个人环境。

提交 PR 时说明问题、行为变化和验证方式；功能修复应附回归测试，纯文档调整无需新增测试。
修改功能、配置或示例时同步中英文文档，并检查相对链接。
不要提交账号、密钥、私人地址、对话导出、临时实测脚本或运行报告。
保留上游来源声明；贡献沿用项目的 AGPL-3.0-only 许可证。

普通问题通过 Issues 反馈，安全问题请使用 [安全报告流程](SECURITY.md)。

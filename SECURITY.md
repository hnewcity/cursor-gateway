# Security Policy / 安全策略

## Reporting a vulnerability

Report vulnerabilities privately through [**Security → Report a vulnerability**](https://github.com/hnewcity/cursor-gateway/security/advisories/new) on the repository, when enabled.
If this option is unavailable, open an issue asking the maintainer to enable private reporting or provide a private
contact channel. Do not include vulnerability details in that public request.

Include the affected version or commit, deployment method, impact, and a minimal reproduction using synthetic data.
Never attach `.env`, `accounts.json`, access / refresh tokens, registry credentials, compaction keys, or raw session logs.
Redact account identifiers, prompts, and tool output from examples.

The latest released version is the maintenance target. Older versions do not have a separate security backport policy.
There is no guaranteed response time; the maintainer will coordinate investigation and disclosure with the reporter.

## Deployment

- Set `CURSOR_DIRECT_API_KEY` before exposing the API to other machines.
- Keep the default loopback binding unless you have configured authenticated access and TLS at a reverse proxy.
- Protect the account directory and its backups. It contains credentials and the compaction key.
- Store publishing credentials in the CI platform's secret store, never in scripts or Git history.
- If a credential is committed, revoke or rotate it first. Removing it from the latest commit does not revoke it.

## 中文说明

如仓库已启用私密漏洞报告，请使用 [**Security → Report a vulnerability**](https://github.com/hnewcity/cursor-gateway/security/advisories/new)。
若没有这个入口，可通过普通 Issue 请求维护者启用私密报告或提供私密联系方式，**不要公开漏洞细节**。

报告中提供版本或提交、部署方式、影响范围，以及使用虚构数据的最小复现。
不要附上 `.env`、账号文件、访问或刷新 token、镜像仓库凭据、压缩密钥或原始会话日志。
示例中的账号信息、提示词和工具输出应先脱敏。

维护以最新发布版本为主，旧版本暂无独立的安全补丁承诺，也不承诺固定响应时间。
对外部署前配置网关密钥及访问控制；通过反向代理提供 TLS，妥善保护账号目录和备份。
发布凭据应放在 CI Secrets 中；若曾进入 Git，应先撤销或轮换，删除文件不能使旧凭据失效。

# [P2] 健康检查把 HTTP 500 当作健康

Telegram 会话断线时，真实 `/healthcheck` handler 返回 HTTP 500。CLI 的 `health_check` 仅观察请求是否抛异常，没有检查状态码，仍返回退出码 0。Docker HEALTHCHECK 因此无法区分健康与已断线的 bot。

## 预期与实际

- 预期：HTTP 500 对应非零检查结果；正常 HTTP 200 对应 0。
- 实际：真实服务端 handler 的 HTTP 500 和 200，经客户端请求边界 mock 传入 CLI，均得到 0。

源码：[CLI 检查](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/__main__.py#L49)、[服务端状态](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L162)。

## 重现

从仓库根目录运行：

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_14_healthcheck_http_status.py -v
```

case 独立实例化真实 Http，模拟 Telegram 会话检查抛 ConnectionError，取得真实 HTTP 500 Response，再通过假 ClientSession 调用真实 CLI 检查。另有 HTTP 200 正常对照。

测试断言当前实际缺陷，**通过表示问题已复现**。本 PR 只新增说明与重现 case；问题修复后需要更新或替换这些断言。

## 验证边界

Telegram 会话和 HTTP 网络传输为 mock；未连接 Telegram、启动真实 HTTP 服务或 Docker 容器。自动 case 共 2 项，不依赖其他重现 PR。

# [P3] 完整下载被显示为仍有剩余

文件大小恰好整除 HTTP block_size，所有分块已完整传输，客户端结束连接。超时清理使用 `size // block_size + 1` 计算总块数，因此多算一个不存在的分块。

## 预期与实际

| 已下载文件 | block_size | 实际下载块数 | 预期剩余 | 实际传给 close 的剩余 |
|---|---|---|---|---|
| 4 字节 | 4 | 1 | 0% | 50% |
| 8 字节 | 4 | 2 | 0% | 33.33% |
| 9 字节，对照 | 4 | 3 | 0% | 0% |

这会使完整传输后的控制消息报告仍有内容未下载。

源码：[块数与百分比计算](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L197)、[关闭时的控制消息](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L224)。

## 重现

从仓库根目录运行：

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_19_completed_block_count.py -v
```

case 使用真实 Http 的分块记录与 `_timeout_handler`。按文件大小记录所有有效分块，在无活动 transport 时直接触发超时回调，捕获传给视频 close 的实际百分比。

测试断言当前实际缺陷，**通过表示问题已复现**。本 PR 只新增说明与重现 case；修复后需要更新或替换这些断言。

## 验证边界

视频 close 为 AsyncMock，不发送 Telegram 控制消息；不下载真实文件、不等待 900 秒，也不启动 HTTP 服务。自动 case 共 2 项，不依赖其他重现 PR。

# [P1] 媒体令牌可越权读取其他 Telegram 文档

## 问题和触发条件

持有一个活跃媒体 URL 时，用户可改变 message_id 并把 token 扩展到超过 64 位，保持 `(message_id << 64) ^ token` 不变。字典授权通过后，HTTP handler 按修改后的消息 ID 获取文档。目标文档必须为 bot 可访问；该问题不会越过 Telegram 自身的访问权限。

源码位置：

- [castbot/utils.py#L15](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/utils.py#L15)
- [castbot/utils.py#L23](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/utils.py#L23)
- [castbot/http.py#L233](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L233)
- [castbot/http.py#L256](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L256)

## 重现 case

只授权虚构的消息 1/token 2，构造消息 2 的令牌，调用真实 HTTP handler。预期拒绝（403）；实际 fake Telegram client 收到 get_message(2)，handler 返回 200 和完整媒体。正常且不相等的消息 2/token 2 被拒绝，作为授权控制对照。

仅添加说明和独立的 unittest 重现文件，使用虚构消息、令牌和内存数据。真实 handler 被执行，Telegram I/O 与响应传输被 mock；不启动服务、不访问网络、无需真实凭据。

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_02_media_token_scope.py -v
```

测试刻意断言当前观察到的缺陷，PASS 表示问题已重现。修复后应替换这些断言为预期行为测试。

## 验证边界

已在 Python 3.14、dfba532 最新锁依赖环境执行：2/2 unittest 方法通过。离线执行；未验证真实 Telegram 或电视/浏览器播放器。没有业务代码修改。

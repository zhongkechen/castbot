# [P1] HTTP Range 的字节数与响应长度不符

## 问题和触发条件

播放器读取范围或拖动进度时，HTTP Range 包含式结束位置被当成排除式上限，而 Content-Length 始终声明完整文件大小。

源码位置：

- [castbot/http.py#L68](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L68)
- [castbot/http.py#L141](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L141)
- [castbot/http.py#L278](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L278)
- [castbot/http.py#L302](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L302)

## 重现 case

使用 8 字节媒体 ABCDEFGH、4 字节分块并调用真实 handler：bytes=2-4 实际 CD（应为 CDE）；bytes=4- 实际 4 字节却声明 8；bytes=0-0 返回空（应为 A）；bytes=0-7 丢失 H。此外 suffix 和超出文件末尾的上限均返回 400。

仅添加说明和独立的 unittest 重现文件，使用虚构消息、令牌和内存数据。真实 handler 被执行，Telegram I/O 与响应传输被 mock；不启动服务、不访问网络、无需真实凭据。

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_04_http_range.py -v
```

测试刻意断言当前观察到的缺陷，PASS 表示问题已重现。修复后应替换这些断言为预期行为测试。

## 验证边界

已在 Python 3.14、dfba532 最新锁依赖环境执行：2/2 unittest 方法通过。离线执行；未验证真实 Telegram 或电视/浏览器播放器。没有业务代码修改。

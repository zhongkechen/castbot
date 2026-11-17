## 问题

`get_message` 的无 TTL 缓存保留旧 Telegram 文件引用。下载返回 `FileReferenceExpired` 后没有重新获取消息；同一视频再次播放仍使用旧引用并再次失败。

本 PR 添加一份问题记录和可独立执行的离线重现 case，审查优先级 **P2**。

## 触发条件

一条已缓存的视频消息；Telegram 在后续文件读取中返回真实 `FileReferenceExpired` 错误类型。case 为消息刷新预置了另一份带新引用的成功响应。

## 预期与实际

- 预期：引用失效时能够重新取得有效文件引用，后续重播不应持续重用失效值。
- 实际：两次重播都抛 `FileReferenceExpired`，两次文件请求都含旧引用；GetMessages 只执行一次，预置的新引用没有被读取。

## 源码位置

- [castbot/client.py:51](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/client.py#L51)
- [castbot/client.py:83](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/client.py#L83)
- [castbot/client.py:92](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/client.py#L92)

## 重现

在仓库根目录、安装项目锁定依赖的环境中运行：

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_13_expired_file_reference.py -v
```

case 构造真实 RawMessage/Document，替换 Telegram RPC 为本地 AsyncMock；连续两次执行真实 get_message → get_block，并检查缓存、请求中的引用及底层 RPC 调用次数。

**测试通过表示当前缺陷已被复现，不代表问题已修复。** case 断言当前实际错误行为；问题修复后需要更新或替换这些断言。

## 验证与限制

本地 Python 3.14 离线运行：**1 项测试通过**。

- 没有连接 Telegram，也没有测量服务器真实引用的过期时长。
- 模拟 RPC 返回已知的引用失效异常；所有文档标识、引用与账户数据均为虚构。

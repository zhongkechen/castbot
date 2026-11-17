# [P2] VLC 认证因合法 TCP 分段而失败

VLC Telnet 启用密码认证，正常认证提示或成功响应在 TCP 上分两次到达。TCP read 不保证一次得到完整协议消息。

预期：同一合法认证字节流无论怎样分段，密码与后续 stop 命令都应按协议处理。实际：banner 首段不以认证 magic 结尾时，应用跳过密码直接发送 stop；认证成功响应只读取前半段时，应用将其当失败并关闭连接。

重现文件直接引用实现中的真实 `_AUTH_MAGIC`、`_AUTH_OK`，先验证完整输入可发送密码及 stop，再将完全相同的字节流分别分段，确认其中一段未被读取、认证失败。

源码：[castbot/devices/vlc.py:54](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/vlc.py#L54)、[castbot/devices/vlc.py:61](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/vlc.py#L61)。

## 重现

在此分支安装项目锁定依赖后，从仓库根目录执行：

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_12_vlc_fragmented_auth.py -v
```

新增文件 `tests/repro_cases/test_12_vlc_fragmented_auth.py` 独立运行，不依赖其他问题 PR 的 helper。测试断言当前观察到的缺陷，**PASS 表示缺陷已复现**；修复该行为后应更新或替换这些断言。本 PR 仅新增问题说明和重现 case，生产代码及 CI 未修改。

## 验证边界

asyncio.open_connection 和读取分段用 mock；不连接 VLC。输入使用相同合法字节流，只改变 TCP chunk 边界。

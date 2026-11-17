# [P2] UPnP 通知无法解析正常令牌

配置 UPnP 并开始播放后，设备使用应用生成的 `/upnp/notify/{local_token}` 回调地址发送通知。地址中的令牌是十六进制字符串。

预期：已登记令牌进入通知处理，正常事件得到成功响应。实际：包含 a–f 的正常令牌返回 400；恰好只含数字的正常令牌先被转成 int，再交给 `int(value, 16)`，抛 TypeError。因此播放状态通知与断流恢复无法工作。

重现文件分别向真实 `UpnpNotifyServer.handle` 提交两个已登记、由真实 `LocalToken` 生成的令牌，并确认正文尚未读取就失败。

源码：[castbot/devices/upnp.py:141](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/upnp.py#L141)、[castbot/devices/upnp.py:144](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/upnp.py#L144)、[castbot/devices/upnp.py:249](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/upnp.py#L249)。

## 重现

在此分支安装项目锁定依赖后，从仓库根目录执行：

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_06_upnp_notify_token.py -v
```

新增文件 `tests/repro_cases/test_06_upnp_notify_token.py` 独立运行，不依赖其他问题 PR 的 helper。测试断言当前观察到的缺陷，**PASS 表示缺陷已复现**；修复该行为后应更新或替换这些断言。本 PR 仅新增问题说明和重现 case，生产代码及 CI 未修改。

## 验证边界

只运行真实 handler 的令牌解析和登记逻辑；请求正文与设备用 mock，不连接 UPnP 设备。

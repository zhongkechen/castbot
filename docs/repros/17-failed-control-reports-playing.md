## 问题

Kodi 的 HTTP 401 被转换为正常返回值，VLC 认证拒绝也正常关闭连接后返回。在把 Telegram 消息发送设为成功 mock 后，真实 PLAY 控制逻辑仍调用 Playing 消息更新和成功回答。

本 PR 添加一份问题记录和可独立执行的离线重现 case，审查优先级 **P2**。

## 触发条件

Kodi RPC 的所有请求返回 401，或 VLC telnet 在密码提交后拒绝认证。

## 预期与实际

- 预期：控制失败应使用户收到失败结果，不能更新为已播放状态。
- 实际：Kodi 四次 RPC 全部 401，VLC 三次连接全部认证拒绝；两个 case 仍以 Playing 开头的文本调用消息更新 mock，callback.answer mock 仍收到 Playing。

## 源码位置

- [castbot/devices/xbmc.py:88](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/xbmc.py#L88)
- [castbot/devices/xbmc.py:121](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/xbmc.py#L121)
- [castbot/devices/vlc.py:63](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/vlc.py#L63)
- [castbot/video.py:194](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L194)

## 重现

在仓库根目录、安装项目锁定依赖的环境中运行：

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_17_failed_control_reports_playing.py -v
```

实例化真实驱动、PlayingVideo、VideoControlButton；把设备网络边界替换为 401 HTTP session 或认证拒绝的 telnet reader/writer，并把 Telegram 消息更新、callback 回答设为成功 mock。执行真实 on_click → play → driver 链，检查驱动失败是否传播以及调用方选择的状态。

**测试通过表示当前缺陷已被复现，不代表问题已修复。** case 断言当前实际错误行为；问题修复后需要更新或替换这些断言。

## 验证与限制

本地 Python 3.14 离线运行：**2 项测试通过**。

- 没有运行真实 Kodi/VLC，也没有使用真实设备密码。
- case 针对 HTTP 401 和完整认证拒绝；未测试 TCP 分段，此问题与分段认证 case 独立。
- 没有执行 Telegram 消息序列化或发送。当前还存在独立的按钮构造故障（第 21 项），实际消息发送会先被它阻断；本 case 隔离发送边界，单独重现驱动错误未向调用方传播的问题。

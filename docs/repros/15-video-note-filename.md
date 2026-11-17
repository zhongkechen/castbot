## 问题

bot 已注册 video_note 消息处理，但 pyrogram_filename 仍访问 VideoNote.file_name。真实 VideoNote 没有该属性；play 只处理 TypeError，AttributeError 会在发送设备播放命令前发生。

本 PR 添加一份问题记录和可独立执行的离线重现 case，审查优先级 **P2**。

## 触发条件

选择一个设备后，对真实 pyrogram.types.VideoNote 对象执行 PlayingVideo.play。

## 预期与实际

- 预期：圆形视频能够进入设备播放流程，其缺少文件名不应阻断播放。
- 实际：抛出包含 file_name 的 AttributeError；设备 stop/play 和播放状态更新均没有执行。

## 源码位置

- [castbot/bot.py:34](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/bot.py#L34)
- [castbot/video.py:188](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L188)
- [castbot/video.py:237](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L237)

## 重现

在仓库根目录、安装项目锁定依赖的环境中运行：

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_15_video_note_filename.py -v
```

构造真实 VideoNote、真实 PlayingVideo 和虚构令牌；仅替换设备与控制消息的外部操作，调用真实 play 并检查异常与未发生的播放命令。

**测试通过表示当前缺陷已被复现，不代表问题已修复。** case 断言当前实际错误行为；问题修复后需要更新或替换这些断言。

## 验证与限制

本地 Python 3.14 离线运行：**1 项测试通过**。

- 没有发送或接收真实 Telegram 视频，也没有连接播放设备。
- case 检查播放入口失败，未模拟任何视频编码或格式兼容性问题。

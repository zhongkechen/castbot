# [P2] 旧视频超时清理注销仍播放新视频的设备

用户在同一已选设备上先播放 A，再切换到 B。A 的连接结束后，其清理仍会在默认 900 秒宽限期后运行。

预期：A 的清理只处理 A 的播放资源，B 及其设备继续有效。实际：A.close 调用共享设备的 on_close，WebDevice 无条件注销同一浏览器；B 仍在应用与 HTTP 播放映射中，却失去了 Web 设备注册。

重现文件创建真实 Http、PlayingVideos 和 WebDevice：A、B 默认共享用户设备，B 有活动 transport，播放 URL 已被浏览器领取；直接运行 A 的真实 HTTP 超时回调后，浏览器注销而 B 仍为活动状态。此 case 聚焦跨播放实例的清理归属，与重复 UPnP 订阅任务问题分别记录。

源码：[castbot/http.py:205](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L205)、[castbot/video.py:224](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L224)、[castbot/devices/web.py:29](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/web.py#L29)、[castbot/devices/chromecast.py:33](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/chromecast.py#L33)、[castbot/devices/upnp.py:233](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/upnp.py#L233)。

## 重现

在此分支安装项目锁定依赖后，从仓库根目录执行：

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_09_stale_playback_cleanup.py -v
```

新增文件 `tests/repro_cases/test_09_stale_playback_cleanup.py` 独立运行，不依赖其他问题 PR 的 helper。测试断言当前观察到的缺陷，**PASS 表示缺陷已复现**；修复该行为后应更新或替换这些断言。本 PR 仅新增问题说明和重现 case，生产代码及 CI 未修改。

## 验证边界

直接模拟到期回调而不等待 900 秒；Telegram 控制消息与 transport 为 mock。自动 case 验证 Web 驱动，不连接真实 Chromecast/UPnP 或浏览器。

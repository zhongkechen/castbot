# [P2] 网页播放后 STOP 没有发出停止指令

网页播放器已通过 poll 领取并开始播放一个 URL，然后用户按 Telegram STOP。

预期：浏览器收到可识别的停止事件并停止当前视频。实际：stop 只清空已经被领取的 `_url_to_play`，后续 poll 与普通无更新情况完全相同，返回 302、空 body；HTML 的 poll 回调没有执行停止的分支。Telegram 控制消息被更新，浏览器却没有收到停止指令。

重现文件通过真实 PlayingVideo.stop、WebDevice、poll handler 验证上述协议行为。手动浏览器 case：配置 Web 设备并打开 `/static/index.html`；登录并播放视频；在视频仍播放时按 Telegram STOP；观察 Telegram 控制消息变化但网页播放持续。

源码：[castbot/devices/web.py:26](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/web.py#L26)、[castbot/devices/web.py:99](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/web.py#L99)、[castbot/static/index.html:30](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/static/index.html#L30)。

## 重现

在此分支安装项目锁定依赖后，从仓库根目录执行：

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_10_web_stop_command.py -v
```

新增文件 `tests/repro_cases/test_10_web_stop_command.py` 独立运行，不依赖其他问题 PR 的 helper。测试断言当前观察到的缺陷，**PASS 表示缺陷已复现**；修复该行为后应更新或替换这些断言。本 PR 仅新增问题说明和重现 case，生产代码及 CI 未修改。

## 验证边界

自动 case 验证服务器协议没有 stop 事件，未执行浏览器 HTML 或真实 Telegram 操作；浏览器表现提供手动步骤。

# [P2] 重复 UPnP 播放遗留旧订阅任务

对同一个 UpnpDevice 连续调用 play(A)、play(B)，然后关闭 B。

预期：替换播放时旧订阅被释放；关闭后没有旧播放遗留的订阅。实际：`_subscribe_task` 被新任务覆盖，A 从未收到 close；on_close 只能关闭 B。真实 SubscribeTask 中，未关闭的任务每 10 秒执行退订/订阅循环，旧通知登记也保留。

重现文件运行真实 UpnpDevice.play/on_close，替换网络服务调用与 SubscribeTask 为记录对象：两个订阅均启动，最终第二个关闭一次，第一个仍启动且关闭次数为 0。

源码：[castbot/devices/upnp.py:205](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/upnp.py#L205)、[castbot/devices/upnp.py:246](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/upnp.py#L246)、[castbot/devices/upnp.py:233](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/devices/upnp.py#L233)。

## 重现

在此分支安装项目锁定依赖后，从仓库根目录执行：

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_11_upnp_subscription_leak.py -v
```

新增文件 `tests/repro_cases/test_11_upnp_subscription_leak.py` 独立运行，不依赖其他问题 PR 的 helper。测试断言当前观察到的缺陷，**PASS 表示缺陷已复现**；修复该行为后应更新或替换这些断言。本 PR 仅新增问题说明和重现 case，生产代码及 CI 未修改。

## 验证边界

SubscribeTask 用生命周期记录对象替代，不启动真实后台循环或联网；自动 case 证明旧对象未被关闭，10 秒循环由原实现直接可见。

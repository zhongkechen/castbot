# [P2] 单个设备发现故障丢失全部正常结果

同时配置至少两个发现器，一个能返回设备，另一个超时或遇到网络连接错误。

预期：健康发现器返回的设备仍可用于设备菜单。实际：超时抛出的 TimeoutError、网络 ConnectionError 穿透 `gather`，整个刷新失败，健康设备结果没有保存。

重现文件并行运行健康与失败 finder，两种场景都确认健康 finder 已执行，但最终 `_devices` 仍为空。超时场景使用合法的 `request_timeout=0`；真实 timeout 上下文的 1 秒期限仅在测试中加速为 0.01 秒，不使用负配置。

源码：[castbot/device.py:103](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/device.py#L103)、[castbot/device.py:112](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/device.py#L112)。

## 重现

在此分支安装项目锁定依赖后，从仓库根目录执行：

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_07_finder_failure_isolation.py -v
```

新增文件 `tests/repro_cases/test_07_finder_failure_isolation.py` 独立运行，不依赖其他问题 PR 的 helper。测试断言当前观察到的缺陷，**PASS 表示缺陷已复现**；修复该行为后应更新或替换这些断言。本 PR 仅新增问题说明和重现 case，生产代码及 CI 未修改。

## 验证边界

发现器输出和网络故障为 mock；使用真实 asyncio/async-timeout 取消机制，不进行 SSDP 或 Chromecast 扫描。

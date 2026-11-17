# [P2] 设备显示名称导致选择解析和标识冲突

配置名称含冒号、逗号、较长中文字符的设备，或两个显示名称相同的设备。

预期：每个设备都能生成有效按钮、准确选择并在恢复控制时保持身份。实际：`TV:Living Room` 的 callback 被误认作旧协议并抛 ValueError；八个“电视机”形成 93 字节 callback，超过 Telegram 的 64 字节限制；同名设备的 callback 完全相同，查找总是返回第一个；`TV, Living Room` 恢复为 `TV`。

重现文件直接调用真实 DeviceSelectButton.get_data()、callback 解析、设备查找和控制文本解析。

源码：[castbot/button.py:139](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/button.py#L139)、[castbot/button.py:221](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/button.py#L221)、[castbot/device.py:118](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/device.py#L118)、[castbot/video.py:129](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/video.py#L129)。

## 重现

在此分支安装项目锁定依赖后，从仓库根目录执行：

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_08_device_name_identifiers.py -v
```

新增文件 `tests/repro_cases/test_08_device_name_identifiers.py` 独立运行，不依赖其他问题 PR 的 helper。测试断言当前观察到的缺陷，**PASS 表示缺陷已复现**；修复该行为后应更新或替换这些断言。本 PR 仅新增问题说明和重现 case，生产代码及 CI 未修改。

## 验证边界

当前依赖版本另有 get_button 的位置参数构造故障；此 case 直接验证 intended callback payload，未声称完整菜单发送会先触发本编码问题。未实际向 Telegram 提交过长 callback；自动 case 验证真实生成字节数与既有 64 字节协议限制，同名与恢复解析均离线执行。

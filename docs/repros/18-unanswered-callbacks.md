## 问题

设备菜单、设备选择和下载重试的成功路径没有调用 callback_query.answer。Telegram 客户端会继续等待按钮回调的回答。

本 PR 添加一份问题记录和可独立执行的离线重现 case，审查优先级 **P3**。

## 触发条件

DEVICE/REFRESH 成功显示菜单、设备选择成功，或下载重试成功完成。

## 预期与实际

- 预期：这些成功操作应及时回答 callback，不应持续等待到客户端超时。
- 实际：三个 case 验证相应业务动作均成功执行，但 callback.answer 一次也没有被 await；菜单 case 同时覆盖 DEVICE 和 REFRESH。

## 源码位置

- [castbot/button.py:123](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/button.py#L123)
- [castbot/button.py:152](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/button.py#L152)
- [castbot/button.py:177](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/button.py#L177)

## 重现

在仓库根目录、安装项目锁定依赖的环境中运行：

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_18_unanswered_callbacks.py -v
```

执行真实三个 Button.on_click，用 AsyncMock 提供成功的业务响应并记录 answer；分别检查业务动作已完成、answer 未被执行。

**测试通过表示当前缺陷已被复现，不代表问题已修复。** case 断言当前实际错误行为；问题修复后需要更新或替换这些断言。

## 验证与限制

本地 Python 3.14 离线运行：**3 项测试通过**。

- 没有连接 Telegram，未实际观察客户端 spinner 或测量客户端超时。
- 该 case 验证成功路径缺少回调回答，不涉及失败路径的提示处理。

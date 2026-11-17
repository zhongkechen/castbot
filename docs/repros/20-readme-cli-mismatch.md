## 问题

README 的 pip 示例使用 -v 1，但实际 -v 是 count 标志，不接收数值参数。README 还写 Python 3.8+，项目声明最低 Python 3.11。

本 PR 添加一份问题记录和可独立执行的离线重现 case，审查优先级 **P3**。

## 触发条件

按 README 的 pip 命令启动；或者按文档声称的最低 Python 版本准备环境。运行命令 case 需要可写 TMPDIR。

## 预期与实际

- 预期：文档中的运行命令能够被 CLI 解析，最低版本说明应与包的 Python requirement 一致。
- 实际：从 README 提取的命令交给真实 entry_point 后退出码为 2，报 unrecognized arguments: 1，未启动业务；版本 case 得到文档 3.8 小于项目 3.11。

## 源码位置

- [README.md:32](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/README.md#L32)
- [README.md:35](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/README.md#L35)
- [castbot/__main__.py:65](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/__main__.py#L65)
- [pyproject.toml:12](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/pyproject.toml#L12)

## 重现

在仓库根目录、安装项目锁定依赖的环境中运行：

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_20_readme_cli_mismatch.py -v
```

直接读取仓库 README 的命令，用 TMPDIR 中最小有效 TOML 替换配置路径；调用真实 entry_point 并捕获解析错误，额外用安全 startup stub 防止意外启动 bot。另从 README 与 pyproject.toml 读取并比较最低版本。

**测试通过表示当前缺陷已被复现，不代表问题已修复。** case 断言当前实际错误行为；问题修复后需要更新或替换这些断言。

## 验证与限制

本地 Python 3.14 离线运行：**2 项测试通过**。

- 没有在 Python 3.8 中执行安装；最低版本差异来自实际 README 与包声明。
- 不创建 Telegram session 或启动 bot，临时配置只含虚构 reproduction 字段。

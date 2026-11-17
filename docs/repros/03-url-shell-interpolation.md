## 问题

URL 正则允许 `&`，下载器把提取到的 URL 原样拼入 `create_subprocess_shell` 的命令字符串。`yt-dlp` 与 `you-get` 都存在这个边界：`&` 被 shell 当作控制操作符，而不是 URL 查询参数的一部分。

本 PR 添加问题说明和可独立运行的离线重现 case，审查优先级 **P1**。该 case 不执行 shell 或攻击命令。

## 触发条件

Telegram 文本入口只允许配置中的 bot admins。需要管理员提交包含 `&` 的链接，或被诱导提交这样的链接；媒体控制权限本身不等于宿主 OS 命令执行权限。

已知应用入口的正则限制了可用 payload 字符。这里验证的是额外无参数命令和合法查询参数被拆开的路径，没有宣称任意形式的 shell 参数都能直接提交。需要将 TMPDIR 指向可写目录，以保存本地输出占位文件。

## 预期与实际

- 预期：提取出的完整 URL 作为下载器的一个参数，`&` 保留在 URL 中。
- 实际：`https://media.invalid/video.mp4&id` 的捕获命令被 shell 词法解析为 URL、独立 `&` 操作符和 `id`；正常 `https://media.invalid/watch?v=dummy&list=dummy` 同样被拆为两个 shell 片段。
- 两个下载后端均观察到同样结果。实际执行时前者可以调用额外的无参数命令，后者会丢失 URL 后半段，并可能使下载命令后台运行。

## 源码位置

- [downloader.py:14](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L14)
- [downloader.py:66](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L66)
- [downloader.py:82](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L82)
- [bot.py:28](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/bot.py#L28)
- [bot.py:35](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/bot.py#L35)

## 重现

在仓库根目录、安装项目锁定依赖后执行：

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_03_url_shell_interpolation.py -v
```

case 先运行真实 `Downloader.parse_link_message`，再运行真实 `Downloader.download`。仅替换 subprocess 边界，创建实际的视频、元数据和缩略图占位文件以完成下载上下文；随后对捕获到的完整命令字符串使用带 shell 操作符识别的 `shlex.shlex`，确认 `&` 是独立操作符、整个 URL 已不再是单个参数。两个测试分别覆盖恶意尾段和正常查询参数，每个测试覆盖两个后端。

**PASS 表示当前缺陷已复现，不代表已修复。** case 断言当前观察到的错误行为；问题修复后需要更新或替换这些断言。

## 验证边界

- 不执行任何 shell、yt-dlp、you-get 或 `id`，没有 OS payload 执行或真实下载。
- 不连接 Telegram、播放设备或外部 URL，所有 URL 和输出数据均为虚构。
- 自动 case 验证 source-to-shell 命令构造与词法边界，没有测量后台下载竞争或实际系统命令影响。

## 问题

下载器无条件对 duration 执行 int()，并把固定的 video1.jpg 路径作为缩略图。缺失 duration 会导致 int(None)；未生成缩略图时仍向后续上传传递不存在的路径。

本 PR 添加一份问题记录和可独立执行的离线重现 case，审查优先级 **P2**。

## 触发条件

下载进程成功且已生成视频、info.json，但元数据 duration 为 null，或缺少缩略图。TMPDIR 必须指向可写目录。

## 预期与实际

- 预期：可选元数据缺失不应使已成功下载的视频失败，也不应把不存在的缩略图路径交给上传。
- 实际：第一个 case 在成功下载后抛 TypeError(NoneType)；第二个 case 确认视频存在，但 DownloadedVideo.thumbnail_filename 指向不存在的文件。

## 源码位置

- [castbot/downloader.py:71](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L71)
- [castbot/downloader.py:78](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L78)
- [castbot/downloader.py:123](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/downloader.py#L123)

## 重现

在仓库根目录、安装项目锁定依赖的环境中运行：

```bash
poetry run python -m unittest discover -s tests/repro_cases -p test_16_optional_download_metadata.py -v
```

在 TMPDIR 中生成实际的视频占位文件及 JSON；仅替换 subprocess 调用为返回成功的本地假进程，再调用真实 Downloader.download，分别检查缺失 duration 和 thumbnail 两种结果。

**测试通过表示当前缺陷已被复现，不代表问题已修复。** case 断言当前实际错误行为；问题修复后需要更新或替换这些断言。

## 验证与限制

本地 Python 3.14 离线运行：**2 项测试通过**。

- 占位文件不包含可播放的视频编码；测试只关注输出文件和元数据消费。
- 不执行 yt-dlp、联网下载或 Telegram 上传；缩略图 case 检查传出的不存在路径。

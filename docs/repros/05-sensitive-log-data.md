# [P2] 日志记录设备密码与可还原媒体令牌

DeviceFinder 的 INFO 日志输出完整设备配置，包括设备 password；流 handler 在 INFO 日志输出可逆 LocalToken 和全部 HTTP 请求 headers。LocalToken 的十六进制字符串包含 message_id 和访问 token，可以反序列化恢复。

触发前提是开启相关日志（镜像 `-vv` 启用 INFO），日志读取者没有对应设备或媒体权限。预期：诊断日志不向这类读取者暴露密码或媒体访问能力。实际：设备密码、访问令牌和敏感请求 header 被原样记录。

case 先捕获真实 WebDeviceFinder 初始化日志中的虚构密码，再调用已授权的真实 Http GET handler，从捕获日志中解析和恢复完整虚构媒体令牌，同时确认虚构 Authorization header 被记录。

源码：[castbot/device.py:62](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/device.py#L62)、[castbot/http.py:285](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L285)、[castbot/http.py:329](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/http.py#L329)、[castbot/utils.py:25](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/castbot/utils.py#L25)、[Dockerfile:26](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/Dockerfile#L26)。

## 重现

在仓库根目录安装锁定依赖后运行：

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_05_sensitive_log_data.py -v
```

新增重现文件独立运行，不依赖其他 PR helper。**PASS 表示当前缺陷或静态配置矛盾已被观察到，不代表问题修复**；对应行为变化后应更新或替换断言。本 PR 只包含说明与重现文件。

## 验证边界

所有密码、令牌、文档引用和 HTTP headers 为虚构值。消息 RPC、stream 写入及 transport 用 mock，不访问网络或真实日志。验证直接输出机制，未验证某部署的日志访问权限；安全严重程度取决于该权限边界。

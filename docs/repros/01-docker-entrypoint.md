# [P1] Docker 默认入口与禁用虚拟环境配置冲突

`POETRY_VIRTUALENVS_CREATE=0` 禁止创建虚拟环境，Dockerfile 的两个安装步骤使用该设置；默认 CMD 却执行 `/app/.venv/bin/castbot`，没有 RUN 步骤创建这一虚拟环境。

触发前提是从干净仓库构建镜像，没有预先存在的 `.venv` 被 COPY 进镜像。预期：默认入口位于安装产生的位置并可执行。实际配置：安装到系统环境，入口引用 `.venv` 下的路径。

自动 case 读取真实 Dockerfile，检查禁止创建虚拟环境、两个安装步骤及虚拟环境入口同时存在。它是**静态配置观察**，不把主机文件状态当成镜像文件状态。

源码：[Dockerfile:4](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/Dockerfile#L4)、[Dockerfile:18](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/Dockerfile#L18)、[Dockerfile:22](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/Dockerfile#L22)、[Dockerfile:26](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/Dockerfile#L26)。

## 重现

在仓库根目录安装锁定依赖后运行：

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_01_docker_entrypoint.py -v
```

新增重现文件独立运行，不依赖其他 PR helper。**PASS 表示当前缺陷或静态配置矛盾已被观察到，不代表问题修复**；对应行为变化后应更新或替换断言。本 PR 只包含说明与重现文件。

## 可选容器重现（本次未执行）

从干净 checkout 构建，使用独立测试镜像标签，不挂载服务目录：

```bash
docker build -t castbot-repro-docker-entrypoint .
docker run --rm --network none --entrypoint /bin/sh castbot-repro-docker-entrypoint \
  -c 'command -v castbot; test -x /app/.venv/bin/castbot'
docker run --rm --network none castbot-repro-docker-entrypoint
```

观察安装的 console script 位置、`.venv` 路径是否可执行以及默认入口的实际启动结果。静态 case 不替代这一运行检查。

## 验证边界

自动测试没有构建或运行 Docker 镜像，不能当作实测 OCI 启动结果。可选容器步骤需要 Docker 和构建时网络访问。

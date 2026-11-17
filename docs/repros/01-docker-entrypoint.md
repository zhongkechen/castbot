# [P1] The Docker command conflicts with disabled virtualenv creation

## Problem and prerequisites

`POETRY_VIRTUALENVS_CREATE=0` disables virtualenv creation for both installation steps in the Dockerfile. The default CMD nevertheless executes `/app/.venv/bin/castbot`, and no RUN step creates that virtualenv.

The prerequisite is an image built from a clean checkout, with no existing `.venv` copied into the image. Expected: the default command points to an executable produced by installation. Observed configuration: installation uses the system environment while the command references a `.venv` path.

The automated case reads the actual Dockerfile and confirms that disabled virtualenv creation, both installation steps, and the virtualenv command coexist. This is a **static configuration observation**; it does not treat the host filesystem as the image filesystem.

## Source locations

- [Dockerfile:4](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/Dockerfile#L4)
- [Dockerfile:18](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/Dockerfile#L18)
- [Dockerfile:22](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/Dockerfile#L22)
- [Dockerfile:26](https://github.com/zhongkechen/castbot/blob/dfba532498d7630a3bb15b0546dc5847f5482ee9/Dockerfile#L26)

## Reproduction

Run from the repository root after installing the locked dependencies:

```bash
poetry install --no-root
poetry run python -m unittest discover -s tests/repro_cases -p test_01_docker_entrypoint.py -v
```

The reproduction file runs independently and does not depend on helpers from other issue PRs. **PASS confirms that the current defect or static configuration conflict has been observed; it does not mean the issue is fixed.** The assertions record the observed behavior and should be updated or replaced after that behavior changes. This PR contains only the problem description and reproduction case; application code and CI are unchanged.

## Optional container reproduction (not executed during this review)

Build from a clean checkout using a dedicated test image tag, without mounting service directories:

```bash
docker build -t castbot-repro-docker-entrypoint .
docker run --rm --network none --entrypoint /bin/sh castbot-repro-docker-entrypoint \
  -c 'command -v castbot; test -x /app/.venv/bin/castbot'
docker run --rm --network none castbot-repro-docker-entrypoint
```

Observe the installed console script location, whether the `.venv` path is executable, and the actual default-command startup result. The static case does not replace this runtime check.

## Validation limits

The automated test neither builds nor runs the Docker image and must not be presented as an observed OCI startup failure. The optional container steps require Docker and network access during the build.

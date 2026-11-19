# Docker entry point

Poetry installs the package into the system Python environment. The default container command and health check both use the installed castbot console script. The regression checks the Dockerfile and the declared package entry point.

Run the regression tests from the repository root after installing the locked dependencies.

```sh
poetry run python -m unittest discover -s tests/repro_cases -p test_01_docker_entrypoint.py -v
```

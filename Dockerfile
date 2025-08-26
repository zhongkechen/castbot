FROM python:3.11

ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=0
#ENV CRYPTOGRAPHY_DONT_BUILD_RUST=1
#ENV PATH="/root/.cargo/bin:${PATH}"

#RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN curl -sSL https://install.python-poetry.org | python -
# RUN python -m pip install --upgrade pip poetry

WORKDIR /app

COPY pyproject.toml poetry.lock README.md /app/

RUN /root/.local/bin/poetry install --no-root

COPY . .

RUN /root/.local/bin/poetry install

HEALTHCHECK CMD ["castbot", "--healthcheck"]

CMD ["castbot", "-vv"]

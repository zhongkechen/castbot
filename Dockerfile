FROM python:3.11

ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=0

RUN curl -sSL https://install.python-poetry.org | python3 -
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml poetry.lock /app/

RUN /root/.local/bin/poetry install

COPY . .

RUN /root/.local/bin/poetry install

HEALTHCHECK CMD ["smart_tv_telegram", "--healthcheck"]

CMD ["smart_tv_telegram"]

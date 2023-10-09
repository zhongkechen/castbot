FROM python:3.11

ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=0

RUN apt-get update && apt-get install -y ffmpeg rustc && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --upgrade pip && python -m pip install poetry

WORKDIR /app

COPY pyproject.toml poetry.lock /app/

RUN poetry install

COPY . .

RUN poetry install

HEALTHCHECK CMD ["castbot", "--healthcheck"]

CMD ["castbot"]

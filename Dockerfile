FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY easy_fints /app/easy_fints

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

COPY .env_example /app/.env_example

RUN mkdir -p /app/logs

EXPOSE 9686

CMD ["uvicorn", "easy_fints.fastapi_app:app", "--host", "0.0.0.0", "--port", "9686"]

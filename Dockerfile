FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
COPY .env_example /app/.env_example

RUN mkdir -p /app/logs

EXPOSE 9686

CMD ["uvicorn", "src.fastapi_app:app", "--host", "0.0.0.0", "--port", "9686"]

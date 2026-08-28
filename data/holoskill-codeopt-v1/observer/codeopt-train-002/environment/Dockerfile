FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir pytest==8.3.3

WORKDIR /app
COPY repo/ /app/

RUN git init -q /app \
 && git -C /app config user.email "task@holoskill.invalid" \
 && git -C /app config user.name "HoloSkill Task" \
 && git -C /app add -A \
 && git -C /app commit -q -m "pinned baseline"

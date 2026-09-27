FROM node:22-bookworm-slim AS contacts-ui-build
WORKDIR /ui
COPY autoevolve-ui/package*.json ./
RUN npm ci --no-audit --no-fund
COPY autoevolve-ui/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg make openssl \
    && rm -rf /var/lib/apt/lists/*

COPY . .
COPY --from=contacts-ui-build /ui/dist /app/autoevolve-ui/dist
RUN make setup-core setup-engines

EXPOSE 8787
CMD [".venv/bin/uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8787"]

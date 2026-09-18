FROM node:22-bookworm-slim AS frontend
WORKDIR /app/road_sense_web/roadsense_frontend
COPY road_sense_web/roadsense_frontend/package.json road_sense_web/roadsense_frontend/pnpm-lock.yaml road_sense_web/roadsense_frontend/pnpm-workspace.yaml ./
COPY road_sense_web/roadsense_frontend/patches ./patches
RUN corepack enable && pnpm install --frozen-lockfile
COPY road_sense_web/roadsense_frontend ./
RUN pnpm vite build --configLoader runner

FROM python:3.10-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 YOLO_CONFIG_DIR=/app/.ultralytics
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*
COPY road_sense_web/roadsense_backend/requirements.txt ./road_sense_web/roadsense_backend/requirements.txt
RUN pip install --no-cache-dir -r road_sense_web/roadsense_backend/requirements.txt
COPY road_sense_web/roadsense_backend ./road_sense_web/roadsense_backend
COPY runs/roadsense_v8 ./runs/roadsense_v8
COPY --from=frontend /app/road_sense_web/roadsense_frontend/dist ./road_sense_web/roadsense_frontend/dist
WORKDIR /app/road_sense_web/roadsense_backend
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}"

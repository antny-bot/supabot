FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY manager/frontend/package*.json ./
RUN npm ci
COPY manager/frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV TZ=Asia/Seoul
RUN apt-get update && apt-get install -y tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 공통 패키지 설치
COPY shared/supabot_common/ ./shared/supabot_common/
RUN pip install --no-cache-dir ./shared/supabot_common

COPY manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY manager/backend/ ./backend/
COPY --from=frontend-builder /frontend/dist ./frontend/dist/

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

# Stage 2: Build Python deps
FROM python:3.10-alpine AS builder

WORKDIR /app

RUN apk add --no-cache --virtual .build-deps \
    gcc \
    musl-dev \
    libffi-dev \
    build-base

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Final image
FROM python:3.10-alpine

LABEL maintainer="coderxiu<coderxiu@qq.com>"
LABEL description="闲鱼AI客服机器人 + Web管理界面"
LABEL version="3.0"

ENV TZ=Asia/Shanghai \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apk add --no-cache tzdata \
    && ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo Asia/Shanghai > /etc/localtime \
    && rm -rf /var/cache/apk/*

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# Copy frontend build output
COPY --from=frontend-builder /app/web/dist /app/web/dist

RUN mkdir -p data prompts

COPY prompts/classify_prompt_example.txt prompts/classify_prompt.txt
COPY prompts/price_prompt_example.txt prompts/price_prompt.txt
COPY prompts/tech_prompt_example.txt prompts/tech_prompt.txt
COPY prompts/default_prompt_example.txt prompts/default_prompt.txt

COPY main.py XianyuAgent.py XianyuApis.py context_manager.py command_parser.py ./
COPY utils/ utils/
COPY server/ server/

EXPOSE 8000

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]

# 备选：容器部署（Northflank 支持源码或容器两种部署方式）
# 若用容器，请把真实 .env 通过环境变量 / Secret 注入，不要写进镜像
FROM python:3.11-slim
WORKDIR /app

# 可选 OCR 依赖（缺失时代码自动跳过，不影响运行）
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data

EXPOSE 3000
# 通过 FB_MODE 环境变量控制 trial / live；.env 用 Secret 挂载到 /app/.env
CMD ["bash", "start.sh"]

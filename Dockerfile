FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MAX_RESULT_HOLES=200000 \
    MAX_BOARD_SIDE=1000000

WORKDIR /app

# 先装依赖（利用 Docker 层缓存）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# 容器启动即启动服务；依赖已在构建时安装完毕
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

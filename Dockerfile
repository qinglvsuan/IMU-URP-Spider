# ═══════════════════════════════════════════════════════════════
# Stage 1: 构建 OCR 专属依赖（ddddocr + opencv + onnxruntime）
# ═══════════════════════════════════════════════════════════════
FROM python:3.12-slim AS ocr-deps

WORKDIR /ocr

# 安装 OCR 所需的系统库
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# 将 OCR 依赖安装到独立路径，不污染主镜像的 site-packages
RUN pip install --no-cache-dir \
        ddddocr==1.6.1 \
    --target /ocr/site-packages


# ═══════════════════════════════════════════════════════════════
# Stage 2: 主应用镜像（精简版，不包含 OCR 重量级依赖）
# ═══════════════════════════════════════════════════════════════
FROM python:3.12-slim

WORKDIR /app

# 安装主应用所需的系统库（lxml 依赖）
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends libxml2 libxslt1.1 libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# 先复制主依赖文件，利用 Docker 层缓存
COPY requirements-main.txt .
RUN pip install --no-cache-dir -r requirements-main.txt

# 从 Stage 1 中拷贝 OCR 依赖到隔离路径
COPY --from=ocr-deps /ocr/site-packages /app/ocr_packages

# 复制源代码
COPY . .

# 创建数据目录（SQLite 存放位置）
RUN mkdir -p /app/data

# 挂载点：data 目录在容器外持久化
VOLUME ["/app/data"]

EXPOSE 5000

# 限制 glibc 内存分配策略，极大降低多线程环境下的内存占用
ENV MALLOC_ARENA_MAX=1
ENV PYTHONUNBUFFERED=1
# ocr_worker.py 专属 Python 路径（只有它能看到 OCR 包）
ENV OCR_PYTHONPATH=/app/ocr_packages

CMD ["python3", "app.py"]

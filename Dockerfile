# ═══════════════════════════════════════════════════════════════
# Stage 1 (ocr-deps): 安装并裁剪 OCR 重型依赖
# ═══════════════════════════════════════════════════════════════
FROM python:3.12-slim AS ocr-deps

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends binutils && \
    rm -rf /var/lib/apt/lists/*

# 安装 OCR 依赖到独立目录
RUN pip install --no-cache-dir ddddocr==1.6.1 --target /ocr/site-packages

# ── 激进裁剪：删除一切不需要的文件 ──
RUN find /ocr/site-packages -type d -name "tests"      -exec rm -rf {} + 2>/dev/null || true && \
    find /ocr/site-packages -type d -name "test"       -exec rm -rf {} + 2>/dev/null || true && \
    find /ocr/site-packages -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /ocr/site-packages -name "*.pyc"  -delete && \
    find /ocr/site-packages -name "*.pyo"  -delete && \
    find /ocr/site-packages -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true && \
    find /ocr/site-packages -name "*.pyi"  -delete && \
    # strip 所有 .so 共享库的调试符号（通常能减小 30-50%）
    find /ocr/site-packages -name "*.so*"  -exec strip --strip-unneeded {} \; 2>/dev/null || true && \
    find /ocr/site-packages -name "*.so.*" -exec strip --strip-unneeded {} \; 2>/dev/null || true

# ═══════════════════════════════════════════════════════════════
# Stage 2: 主应用镜像（精简版）
# ═══════════════════════════════════════════════════════════════
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（lxml 需要 libxml2；OCR .so 需要 libgomp）
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends libxml2 libxslt1.1 libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# 安装主应用依赖（无 OCR）
COPY requirements-main.txt .
RUN pip install --no-cache-dir -r requirements-main.txt && \
    # 删除 pip 本身（运行时不需要，节省 ~12MB）
    pip uninstall -y pip && \
    find /usr/local/lib -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local/lib -name "*.pyc" -delete

# 从 Stage 1 拷贝裁剪后的 OCR 依赖
COPY --from=ocr-deps /ocr/site-packages /app/ocr_packages

# 复制源代码
COPY . .

RUN mkdir -p /app/data

VOLUME ["/app/data"]
EXPOSE 5000

ENV MALLOC_ARENA_MAX=1
ENV PYTHONUNBUFFERED=1
ENV OCR_PYTHONPATH=/app/ocr_packages

CMD ["python3", "app.py"]

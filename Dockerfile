# ── 构建阶段 ─────────────────────────────────────────────────
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（lxml 需要）
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends libxml2 libxslt1.1 && \
    rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源代码
COPY . .

# 创建数据目录（SQLite 存放位置）
RUN mkdir -p /app/data

# 挂载点：.env 和 data 目录在容器外持久化
VOLUME ["/app/data"]

EXPOSE 5000

# 使用环境变量 PYTHONUNBUFFERED=1 保证日志实时输出
ENV PYTHONUNBUFFERED=1
# 限制 glibc 内存分配策略，极大降低多线程环境下的内存占用 (从 ~120M 降至 ~60M)
ENV MALLOC_ARENA_MAX=1

CMD ["python3", "app.py"]

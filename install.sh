#!/bin/bash
# ============================================================
# IMU Spider — 一键部署脚本 (Ubuntu)
# ============================================================
set -e

echo "==============================="
echo " 内蒙古大学教务爬虫 — 安装脚本"
echo "==============================="

# 更新包列表
sudo apt-get update -qq

# 安装 Python3 和 pip（Ubuntu 通常已预装）
if ! command -v python3 &> /dev/null; then
    echo "安装 Python3..."
    sudo apt-get install -y python3 python3-pip
fi

# 安装 pip 依赖
echo "安装 Python 依赖..."
pip3 install -r requirements.txt --quiet

# 创建数据目录
mkdir -p data

echo ""
echo "✅ 依赖安装完成"
echo ""
echo "接下来："
echo "  1. 编辑 .env 文件配置通知方式"
echo "  2. 运行: python3 app.py"
echo "  或使用 systemd 服务（推荐）: sudo systemctl start imu-spider"
echo ""

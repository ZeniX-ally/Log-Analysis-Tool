#!/bin/bash
# ==========================================
# NEXUS FCT Dashboard - 调试启动脚本 (Ubuntu)
# ==========================================

# 1. 获取当前脚本所在绝对路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." &> /dev/null && pwd )"
cd "$PROJECT_DIR"

echo "[中枢系统] 进入工程目录: $PROJECT_DIR"

# 2. 检查并激活虚拟环境
if [ -d "venv" ]; then
    echo "[中枢系统] 激活 Python 虚拟环境..."
    source venv/bin/activate
else
    echo "[警告] 未检测到 venv 目录，请先执行离线依赖安装！"
    exit 1
fi

# 3. 检查 Gunicorn 是否安装 (Ubuntu 生产环境依赖)
if ! command -v gunicorn &> /dev/null; then
    echo "[警告] gunicorn 未安装！请运行: pip install gunicorn==20.1.0"
    exit 1
fi

# 4. 以调试模式启动 Gunicorn (绑定全网卡 0.0.0.0，允许边缘机推流)
echo "[中枢系统] 启动 FCT 数据中枢 (Gunicorn)..."
exec gunicorn --workers 4 \
              --bind 0.0.0.0:59488 \
              --access-logfile - \
              --error-logfile - \
              "backend.app:app"

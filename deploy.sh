#!/bin/bash
set -e

# ==========================================
# Log Analysis Tool - 一键部署脚本 (Linux)
# ==========================================
# 支持: Ubuntu 20.04+, Debian 11+, CentOS 8+
# 功能: 自动安装依赖、配置服务、启动应用
# ==========================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置变量
SERVER_PORT=59488
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_DIR="$PROJECT_ROOT/venv"
SERVICE_NAME="log-analysis-tool.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

# 打印函数
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "\n${GREEN}>>> $1${NC}"
}

# 检查是否为 root 用户
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_warn "检测到非 root 用户，可能需要 sudo 权限。"
        print_warn "如果安装依赖或配置服务失败，请使用 sudo 运行此脚本。"
    fi
}

# 检测系统发行版
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
        print_info "检测到系统: $OS $OS_VERSION"
    else
        print_error "无法检测系统发行版"
        exit 1
    fi
}

# 安装系统依赖
install_system_deps() {
    print_step "安装系统依赖..."

    case $OS in
        ubuntu|debian)
            sudo apt-get update -q
            sudo apt-get install -y -q python3 python3-pip python3-venv git curl ufw
            ;;
        centos|rhel|rocky)
            sudo yum install -y -q python3 python3-pip python3-venv git curl firewalld
            ;;
        *)
            print_warn "不支持的系统: $OS，请手动安装 Python3、pip 和 git"
            ;;
    esac
    print_info "系统依赖安装完成"
}

# 创建虚拟环境
setup_venv() {
    print_step "配置 Python 虚拟环境..."

    if [ -d "$VENV_DIR" ]; then
        print_warn "虚拟环境已存在，跳过创建"
    else
        python3 -m venv "$VENV_DIR"
        print_info "虚拟环境创建完成"
    fi

    source "$VENV_DIR/bin/activate"
    print_info "虚拟环境已激活"
}

# 安装 Python 依赖
install_python_deps() {
    print_step "安装 Python 依赖..."

    if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
        print_error "未找到 requirements.txt"
        exit 1
    fi

    pip install --upgrade pip -q
    pip install -r "$PROJECT_ROOT/requirements.txt" -q
    print_info "Python 依赖安装完成"
}

# 创建必要目录
create_dirs() {
    print_step "创建必要目录..."

    mkdir -p "$PROJECT_ROOT/cache"
    mkdir -p "$PROJECT_ROOT/data/logs"

    # 设置目录权限
    sudo chown -R $USER:$USER "$PROJECT_ROOT/cache"
    sudo chown -R $USER:$USER "$PROJECT_ROOT/data"
    sudo chmod -R 755 "$PROJECT_ROOT/cache"
    sudo chmod -R 755 "$PROJECT_ROOT/data"

    print_info "目录创建完成"
}

# 配置防火墙
setup_firewall() {
    print_step "配置防火墙..."

    if command -v ufw &> /dev/null; then
        sudo ufw allow $SERVER_PORT/tcp > /dev/null 2>&1 || true
        sudo ufw reload > /dev/null 2>&1 || true
        print_info "UFW 防火墙已配置，开放端口 $SERVER_PORT"
    elif command -v firewall-cmd &> /dev/null; then
        sudo firewall-cmd --permanent --add-port=$SERVER_PORT/tcp > /dev/null 2>&1 || true
        sudo firewall-cmd --reload > /dev/null 2>&1 || true
        print_info "Firewalld 已配置，开放端口 $SERVER_PORT"
    else
        print_warn "未检测到防火墙，请手动开放端口 $SERVER_PORT"
    fi
}

# 配置 Systemd 服务
setup_systemd() {
    print_step "配置 Systemd 服务..."

    # 生成 service 文件
    cat > "$PROJECT_ROOT/deploy/$SERVICE_NAME" <<EOF
[Unit]
Description=Log Analysis Tool - FCT Log Analysis Dashboard
After=network.target

[Service]
User=$USER
Group=$USER
WorkingDirectory=$PROJECT_ROOT
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/gunicorn --workers 4 --timeout 120 --bind 0.0.0.0:$SERVER_PORT "backend.app:app"
Restart=always
RestartSec=3
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=log-analysis-tool

[Install]
WantedBy=multi-user.target
EOF

    # 安装服务
    sudo cp "$PROJECT_ROOT/deploy/$SERVICE_NAME" "$SERVICE_PATH"
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME > /dev/null

    print_info "Systemd 服务配置完成"
}

# 启动服务
start_service() {
    print_step "启动服务..."

    sudo systemctl restart $SERVICE_NAME
    sleep 2

    # 检查服务状态
    if systemctl is-active --quiet $SERVICE_NAME; then
        print_info "服务启动成功!"
    else
        print_error "服务启动失败，请查看日志: sudo journalctl -u $SERVICE_NAME -n 50"
        exit 1
    fi
}

# 显示完成信息
show_complete() {
    local IP=$(hostname -I | awk '{print $1}')
    echo -e "\n"
    echo "=========================================="
    echo -e "${GREEN}🎉 部署成功！${NC}"
    echo "=========================================="
    echo "  项目路径: $PROJECT_ROOT"
    echo "  访问地址: http://$IP:$SERVER_PORT"
    echo "  本地访问: http://localhost:$SERVER_PORT"
    echo ""
    echo "  服务管理命令:"
    echo "  - 停止: sudo systemctl stop $SERVICE_NAME"
    echo "  - 启动: sudo systemctl start $SERVICE_NAME"
    echo "  - 重启: sudo systemctl restart $SERVICE_NAME"
    echo "  - 查看日志: sudo journalctl -u $SERVICE_NAME -f"
    echo "=========================================="
}

# ==========================================
# 主程序
# ==========================================
clear
echo "=========================================="
echo " Log Analysis Tool - 一键部署"
echo "=========================================="
echo ""

check_root
detect_os
install_system_deps
setup_venv
install_python_deps
create_dirs
setup_firewall
setup_systemd
start_service
show_complete

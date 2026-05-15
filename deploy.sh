#!/bin/bash
set -e

# ==========================================
# NEXUS FCT Dashboard - Linux 一键部署脚本
# ==========================================
# 支持: Ubuntu 20.04+, Debian 11+, CentOS 8+/RHEL/Rocky
# 用法: chmod +x deploy.sh && ./deploy.sh
# 功能: 自动安装依赖、配置防火墙、创建systemd服务、启动应用
# ==========================================

# ---------- 颜色定义 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ---------- 配置变量 ----------
SERVER_PORT=59488
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_DIR="$PROJECT_ROOT/venv"
SERVICE_NAME="nexus-fct.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

# ---------- 打印函数 ----------
print_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_step()  { echo -e "\n${BLUE}>>> $1${NC}"; }
print_ok()    { echo -e "${GREEN}  ✓ $1${NC}"; }

# ---------- 1. 检查 root/sudo ----------
check_privilege() {
    print_step "检查执行权限..."
    if [ "$EUID" -eq 0 ]; then
        print_warn "当前以 root 运行，建议用普通用户 + sudo 方式执行"
        SUDO_CMD=""
    elif command -v sudo &> /dev/null; then
        SUDO_CMD="sudo"
        print_ok "检测到 sudo，将自动提权执行系统级操作"
    else
        print_error "非 root 用户且未安装 sudo，无法配置系统服务"
        exit 1
    fi
}

# ---------- 2. 检测系统 ----------
detect_os() {
    print_step "检测操作系统..."
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
        print_ok "系统: $OS $OS_VERSION"
    else
        print_error "无法检测系统发行版"
        exit 1
    fi
}

# ---------- 3. 安装系统依赖 ----------
install_system_deps() {
    print_step "安装系统依赖..."

    case $OS in
        ubuntu|debian)
            $SUDO_CMD apt-get update -qq
            $SUDO_CMD apt-get install -y -qq python3 python3-pip python3-venv git curl ufw
            ;;
        centos|rhel|rocky|almalinux|fedora)
            if command -v dnf &> /dev/null; then
                $SUDO_CMD dnf install -y -q python3 python3-pip python3-venv git curl firewalld
            else
                $SUDO_CMD yum install -y -q python3 python3-pip python3-venv git curl firewalld
            fi
            ;;
        *)
            print_warn "不支持的系统: $OS，请手动安装 Python3、pip、git"
            ;;
    esac
    print_ok "系统依赖安装完成"
}

# ---------- 4. 创建虚拟环境 ----------
setup_venv() {
    print_step "配置 Python 虚拟环境..."

    if [ -d "$VENV_DIR" ]; then
        print_warn "虚拟环境已存在，跳过创建"
    else
        python3 -m venv "$VENV_DIR"
        print_ok "虚拟环境创建完成: $VENV_DIR"
    fi

    source "$VENV_DIR/bin/activate"
    print_ok "虚拟环境已激活"
}

# ---------- 5. 安装 Python 依赖 ----------
install_python_deps() {
    print_step "安装 Python 依赖..."

    if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
        print_error "未找到 requirements.txt"
        exit 1
    fi

    pip install --upgrade pip -q
    pip install -r "$PROJECT_ROOT/requirements.txt" -q
    print_ok "Python 依赖安装完成"
}

# ---------- 6. 创建必要目录 ----------
create_dirs() {
    print_step "创建数据目录..."

    mkdir -p "$PROJECT_ROOT/cache"
    mkdir -p "$PROJECT_ROOT/data/logs"

    $SUDO_CMD chown -R $USER:$USER "$PROJECT_ROOT/cache" 2>/dev/null || true
    $SUDO_CMD chown -R $USER:$USER "$PROJECT_ROOT/data" 2>/dev/null || true
    chmod -R 755 "$PROJECT_ROOT/cache"
    chmod -R 755 "$PROJECT_ROOT/data"

    print_ok "目录创建完成"
}

# ---------- 7. 配置防火墙 ----------
setup_firewall() {
    print_step "配置防火墙..."

    if command -v ufw &> /dev/null; then
        $SUDO_CMD ufw allow $SERVER_PORT/tcp > /dev/null 2>&1 || true
        $SUDO_CMD ufw reload > /dev/null 2>&1 || true
        print_ok "UFW 防火墙已配置，开放端口 $SERVER_PORT"
    elif command -v firewall-cmd &> /dev/null; then
        $SUDO_CMD firewall-cmd --permanent --add-port=$SERVER_PORT/tcp > /dev/null 2>&1 || true
        $SUDO_CMD firewall-cmd --reload > /dev/null 2>&1 || true
        print_ok "Firewalld 已配置，开放端口 $SERVER_PORT"
    else
        print_warn "未检测到防火墙，请手动开放端口 $SERVER_PORT"
    fi
}

# ---------- 8. 生成并配置 Systemd 服务 ----------
setup_systemd() {
    print_step "配置 Systemd 服务..."

    # 生成 service 文件到项目目录
    cat > "$PROJECT_ROOT/deploy/$SERVICE_NAME" <<EOF
[Unit]
Description=NEXUS FCT Log Analysis Dashboard Service
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
SyslogIdentifier=nexus-fct

[Install]
WantedBy=multi-user.target
EOF

    # 安装到系统
    $SUDO_CMD cp "$PROJECT_ROOT/deploy/$SERVICE_NAME" "$SERVICE_PATH"
    $SUDO_CMD systemctl daemon-reload
    $SUDO_CMD systemctl enable $SERVICE_NAME > /dev/null 2>&1

    print_ok "Systemd 服务配置完成: $SERVICE_NAME"
}

# ---------- 9. 启动服务 ----------
start_service() {
    print_step "启动服务..."

    $SUDO_CMD systemctl restart $SERVICE_NAME
    sleep 2

    if systemctl is-active --quiet $SERVICE_NAME; then
        print_ok "服务启动成功!"
    else
        print_error "服务启动失败"
        echo ""
        echo "排查命令:"
        echo "  sudo journalctl -u $SERVICE_NAME -n 50"
        echo "  sudo systemctl status $SERVICE_NAME"
        exit 1
    fi
}

# ---------- 10. 健康检查 ----------
health_check() {
    print_step "执行健康检查..."

    local IP=$(hostname -I | awk '{print $1}')
    local HEALTH_URL="http://localhost:$SERVER_PORT"

    sleep 1
    if curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" | grep -q "200\|302"; then
        print_ok "HTTP 服务响应正常"
    else
        print_warn "HTTP 健康检查未通过，服务可能仍在启动中"
    fi
}

# ---------- 11. 显示完成信息 ----------
show_complete() {
    local IP=$(hostname -I | awk '{print $1}')

    echo ""
    echo "=========================================="
    echo -e "${GREEN}  NEXUS FCT Dashboard 部署成功！${NC}"
    echo "=========================================="
    echo ""
    echo "  项目路径: $PROJECT_ROOT"
    echo "  访问地址: http://$IP:$SERVER_PORT"
    echo "  本地访问: http://localhost:$SERVER_PORT"
    echo ""
    echo "  服务管理命令:"
    echo "    停止:   sudo systemctl stop $SERVICE_NAME"
    echo "    启动:   sudo systemctl start $SERVICE_NAME"
    echo "    重启:   sudo systemctl restart $SERVICE_NAME"
    echo "    状态:   sudo systemctl status $SERVICE_NAME"
    echo "    日志:   sudo journalctl -u $SERVICE_NAME -f"
    echo ""
    echo "  调试启动（不经过 systemd）:"
    echo "    source $VENV_DIR/bin/activate"
    echo "    gunicorn --workers 2 --bind 0.0.0.0:$SERVER_PORT backend.app:app"
    echo ""
    echo "  终端监控仪表盘（另开终端运行）:"
    echo "    source $VENV_DIR/bin/activate"
    echo "    python tools/server_monitor.py --host 0.0.0.0 --port $SERVER_PORT"
    echo "=========================================="
}

# ==========================================
# 主程序
# ==========================================
clear
echo "=========================================="
echo "  NEXUS FCT Dashboard - Linux 一键部署"
echo "=========================================="
echo ""

check_privilege
detect_os
install_system_deps
setup_venv
install_python_deps
create_dirs
setup_firewall
setup_systemd
start_service
health_check
show_complete

#!/bin/bash
set -e

# ============================================================
# NEXUS FCT Dashboard - Linux 主服务器一键部署脚本
# ============================================================
# 用法: 将整个 deploy_package 上传到服务器，然后:
#       chmod +x deploy.sh && sudo ./deploy.sh
#
# 功能:
#   1. 自动安装 Python3 + pip + venv
#   2. 创建虚拟环境并安装依赖
#   3. 创建 systemd 服务（开机自启 + 进程守护）
#   4. 配置防火墙
#   5. 可选: Nginx 反向代理
#   6. 健康检查
# ============================================================

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
SERVER_PORT=59488
VENV_DIR="$PROJECT_ROOT/venv"
SERVICE_NAME="nexus-fct"
LOG_DIR="/var/log/nexus-fct"
DATA_DIR="$PROJECT_ROOT/data"

print_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_step()  { echo -e "\n${BLUE}══════════════════════════════════${NC}\n${BLUE}  $1${NC}\n${BLUE}══════════════════════════════════${NC}"; }
print_ok()    { echo -e "${GREEN}  \u2713 $1${NC}"; }

preflight() {
    print_step "前置检查"
    if [ "$EUID" -ne 0 ]; then
        if command -v sudo &> /dev/null; then
            print_warn "需要 root 权限，自动通过 sudo 重新执行..."
            exec sudo bash "$0" "$@"
        fi
        print_error "请以 root 或 sudo 运行: sudo bash $0"
        exit 1
    fi
    if [ ! -f "$PROJECT_ROOT/backend/app.py" ]; then
        print_error "未找到 backend/app.py，请在 deploy_package 目录执行"
        exit 1
    fi
    print_ok "部署路径: $PROJECT_ROOT"
    print_ok "部署版本: $(date +%Y%m%d)"
}

detect_os() {
    print_step "检测操作系统"
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        print_ok "发行版: $OS $VERSION_ID"
    else
        print_error "无法检测系统发行版"
        exit 1
    fi
}

install_system_deps() {
    print_step "安装系统依赖"
    case $OS in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip python3-venv curl ufw
            ;;
        centos|rhel|rocky|almalinux|fedora)
            if command -v dnf &> /dev/null; then
                dnf install -y -q python3 python3-pip python3-venv curl firewalld
            else
                yum install -y -q python3 python3-pip python3-venv curl firewalld
            fi
            ;;
        *)
            print_warn "未知发行版 $OS，尝试用 pip 安装依赖..."
            if ! command -v python3 &> /dev/null; then
                print_error "请手动安装 Python3"
                exit 1
            fi
            ;;
    esac
    python3 -m ensurepip --upgrade 2>/dev/null || true
    print_ok "系统依赖安装完成"
}

create_dirs() {
    print_step "创建运行目录"
    mkdir -p "$DATA_DIR/logs" "$PROJECT_ROOT/cache" "$LOG_DIR"
    chmod -R 755 "$DATA_DIR" "$PROJECT_ROOT/cache" "$LOG_DIR"
    print_ok "数据目录: $DATA_DIR/logs"
    print_ok "日志目录: $LOG_DIR"
}

setup_venv() {
    print_step "配置 Python 虚拟环境"
    if [ -d "$VENV_DIR" ]; then
        print_warn "虚拟环境已存在，跳过创建"
    else
        python3 -m venv "$VENV_DIR"
        print_ok "虚拟环境创建完成"
    fi
    source "$VENV_DIR/bin/activate"
}

install_python_deps() {
    print_step "安装 Python 依赖"
    if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
        print_error "未找到 requirements.txt"
        exit 1
    fi
    pip install --upgrade pip -q
    pip install -r "$PROJECT_ROOT/requirements.txt" -q
    print_ok "Python 依赖安装完成"
    print_ok "  - Flask (Web 框架)"
    print_ok "  - gunicorn (WSGI 服务器)"
    print_ok "  - rich (终端仪表盘)"
    print_ok "  - psutil (系统监控)"
}

setup_firewall() {
    print_step "配置防火墙 (端口 $SERVER_PORT)"
    if command -v ufw &> /dev/null; then
        ufw allow "$SERVER_PORT"/tcp > /dev/null 2>&1 || true
        if ufw status | grep -q inactive 2>/dev/null; then
            print_warn "UFW 未启用，跳过（不影响运行）"
        else
            print_ok "UFW 已开放端口 $SERVER_PORT"
        fi
    elif command -v firewall-cmd &> /dev/null; then
        firewall-cmd --permanent --add-port="$SERVER_PORT"/tcp > /dev/null 2>&1 || true
        firewall-cmd --reload > /dev/null 2>&1 || true
        print_ok "firewalld 已开放端口 $SERVER_PORT"
    else
        print_warn "未检测到防火墙工具，请检查云服务商安全组设置"
    fi
}

setup_systemd() {
    print_step "配置 Systemd 服务 (开机自启 + 进程守护)"
    local SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

    cat > "$SERVICE_PATH" <<SERVICEEOF
[Unit]
Description=NEXUS FCT Log Analysis Dashboard
After=network.target

[Service]
Type=simple
User=$(logname 2>/dev/null || echo 'root')
Group=$(logname 2>/dev/null || echo 'root')
WorkingDirectory=$PROJECT_ROOT
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/gunicorn --workers 4 --timeout 120 --bind 0.0.0.0:$SERVER_PORT "backend.app:app"
Restart=always
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=3
StandardOutput=append:$LOG_DIR/access.log
StandardError=append:$LOG_DIR/error.log

[Install]
WantedBy=multi-user.target
SERVICEEOF

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME" > /dev/null 2>&1
    print_ok "Systemd 服务配置完成: $SERVICE_NAME"
}

start_service() {
    print_step "启动服务"
    systemctl restart "$SERVICE_NAME"
    sleep 3
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_ok "nexus-fct 服务运行中!"
    else
        print_error "服务启动失败，查看日志:"
        echo "  sudo journalctl -u $SERVICE_NAME -n 30 --no-pager"
        echo "  sudo tail -50 $LOG_DIR/error.log"
        exit 1
    fi
}

health_check() {
    print_step "执行健康检查"
    local URL="http://127.0.0.1:$SERVER_PORT"
    for i in {1..5}; do
        if curl -s -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null | grep -q "200\|302"; then
            print_ok "HTTP 服务正常 (200)"
            break
        fi
        if [ $i -eq 5 ]; then
            print_warn "HTTP 检查超时，稍后运行: curl -I $URL"
        fi
        sleep 1
    done
}

show_complete() {
    local IP=$(hostname -I | awk '{print $1}')
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  \uD83D\uDE80 NEXUS FCT Dashboard 部署成功！${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo -e "  ${CYAN}访问地址:${NC}   http://$IP:$SERVER_PORT"
    echo ""
    echo -e "  ${BLUE}服务管理${NC}"
    echo -e "    sudo systemctl start/stop/restart/status $SERVICE_NAME"
    echo -e "    sudo journalctl -u $SERVICE_NAME -f"
    echo ""
    echo -e "  ${BLUE}飞书集成${NC}"
    echo -e "    打开页面后点击 \u2699\uFE0F 齿轮图标配置 Webhook"
    echo -e "    如需将飞书Bot独立部署到其他机器:"
    echo -e "    ./deploy_feishu.sh --server http://$IP:$SERVER_PORT"
    echo ""
    echo -e "  ${BLUE}API 清单${NC}"
    echo -e "    GET  /api/stats              效能统计"
    echo -e "    GET  /api/recent              最新日志"
    echo -e "    GET  /api/limit/compare       限值比对"
    echo -e "    GET  /api/alerts/risk         风险预警"
    echo -e "    GET  /api/feishu/webhook      飞书配置"
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo ""
}

clear
echo ""
echo -e "${GREEN}  \u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557${NC}"
echo -e "${GREEN}  \u2551   NEXUS FCT Dashboard             \u2551${NC}"
echo -e "${GREEN}  \u2551   Linux 一键部署脚本               \u2551${NC}"
echo -e "${GREEN}  \u2551   \u9ed1\u7891                             \u2551${NC}"
echo -e "${GREEN}  \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d${NC}"
echo ""

preflight "$@"
detect_os
install_system_deps
create_dirs
setup_venv
install_python_deps
setup_firewall
setup_systemd
start_service
health_check
show_complete
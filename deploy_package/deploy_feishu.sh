#!/bin/bash
set -e

# ============================================================
# NEXUS FCT 飞书 Bot 独立部署脚本
# ============================================================
# 部署到 FCT6 机器（Linux），从主服务器拉取数据并推送飞书通知
#
# 用法:
#   chmod +x deploy_feishu.sh
#   sudo ./deploy_feishu.sh --server http://172.28.55.66:59488
#
# 参数:
#   --server   主服务器地址 (必填)
#   --port     本地端口 (默认 59489)
# ============================================================

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
SERVER_URL=""
BOT_PORT=59489
SERVICE_NAME="nexus-feishu-bot"
LOG_DIR="/var/log/nexus-feishu"
VENV_DIR="$PROJECT_ROOT/venv_feishu"

print_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_step()  { echo -e "\n${BLUE}══════════════════════════════════${NC}\n${BLUE}  $1${NC}\n${BLUE}══════════════════════════════════${NC}"; }
print_ok()    { echo -e "${GREEN}  \u2713 $1${NC}"; }

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --server) SERVER_URL="$2"; shift 2 ;;
            --port) BOT_PORT="$2"; shift 2 ;;
            *) print_error "未知参数: $1"; exit 1 ;;
        esac
    done
    if [ -z "$SERVER_URL" ]; then
        print_error "请指定主服务器地址: --server http://IP:PORT"
        exit 1
    fi
}

preflight() {
    print_step "前置检查"
    if [ "$EUID" -ne 0 ]; then
        if command -v sudo &> /dev/null; then
            exec sudo bash "$0" "$@"
        fi
        print_error "请以 root 或 sudo 运行"
        exit 1
    fi
    if [ ! -f "$PROJECT_ROOT/feishu_service.py" ]; then
        print_error "未找到 feishu_service.py，请在 deploy_package 目录执行"
        exit 1
    fi
    print_ok "部署路径: $PROJECT_ROOT"
    print_ok "主服务器: $SERVER_URL"
    print_ok "本地端口: $BOT_PORT"
}

detect_os() {
    print_step "检测操作系统"
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        print_ok "发行版: $OS $VERSION_ID"
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
    esac
    print_ok "系统依赖安装完成"
}

create_dirs() {
    print_step "创建运行目录"
    mkdir -p "$PROJECT_ROOT/data" "$LOG_DIR"
    chmod -R 755 "$PROJECT_ROOT/data" "$LOG_DIR"
    print_ok "数据目录: $PROJECT_ROOT/data"
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
    pip install --upgrade pip -q
    print_ok "依赖安装完成 (飞书 Bot 无额外依赖)"
}

setup_firewall() {
    print_step "配置防火墙 (端口 $BOT_PORT)"
    if command -v ufw &> /dev/null; then
        ufw allow "$BOT_PORT"/tcp > /dev/null 2>&1 || true
        if ufw status | grep -q inactive 2>/dev/null; then
            print_warn "UFW 未启用"
        else
            print_ok "UFW 已开放端口 $BOT_PORT"
        fi
    elif command -v firewall-cmd &> /dev/null; then
        firewall-cmd --permanent --add-port="$BOT_PORT"/tcp > /dev/null 2>&1 || true
        firewall-cmd --reload > /dev/null 2>&1 || true
        print_ok "firewalld 已开放端口 $BOT_PORT"
    fi
}

setup_systemd() {
    print_step "配置 Systemd 服务 (开机自启 + 进程守护)"
    local SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

    cat > "$SERVICE_PATH" <<SERVICEEOF
[Unit]
Description=NEXUS FCT Feishu Bot Service (FCT6)
After=network.target

[Service]
Type=simple
User=$(logname 2>/dev/null || echo 'root')
Group=$(logname 2>/dev/null || echo 'root')
WorkingDirectory=$PROJECT_ROOT
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python3 feishu_service.py --server $SERVER_URL --port $BOT_PORT
Restart=always
RestartSec=10
StartLimitIntervalSec=60
StartLimitBurst=3
StandardOutput=append:$LOG_DIR/output.log
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
        print_ok "飞书 Bot 服务运行中!"
    else
        print_error "服务启动失败，查看日志:"
        echo "  sudo journalctl -u $SERVICE_NAME -n 30 --no-pager"
        exit 1
    fi
}

show_complete() {
    local IP=$(hostname -I | awk '{print $1}')
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  \uD83D\uDE80 NEXUS FCT \u98DE\u4E66 Bot \u90E8\u7F72\u6210\u529F\uFF01${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo -e "  ${CYAN}\u914D\u7F6E\u9875\u9762:${NC}   http://$IP:$BOT_PORT"
    echo -e "  ${CYAN}\u4E3B\u670D\u52A1\u5668:${NC}   $SERVER_URL"
    echo ""
    echo -e "  ${BLUE}\u670D\u52A1\u7BA1\u7406${NC}"
    echo -e "    sudo systemctl start/stop/restart/status $SERVICE_NAME"
    echo -e "    sudo journalctl -u $SERVICE_NAME -f"
    echo ""
    echo -e "  ${BLUE}\u98CE\u9669\u9884\u8B66${NC}"
    echo -e "    \u6BCF 30 \u79D2\u8F6E\u8BE2\u4E3B\u670D\u52A1\u5668\uFF0C\u65B0\u9884\u8B66\u81EA\u52A8\u63A8\u9001\u98DE\u4E66"
    echo -e "  ${BLUE}\u5B9A\u65F6\u65E5\u62A5${NC}"
    echo -e "    \u6BCF\u65E5 08:00 \u81EA\u52A8\u53D1\u9001\u524D\u4E00\u65E5\u6548\u80FD\u7EDF\u8BA1"
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo ""
}

clear
echo ""
echo -e "${GREEN}  \u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557${NC}"
echo -e "${GREEN}  \u2551   NEXUS FCT \u98DE\u4E66 Bot               \u2551${NC}"
echo -e "${GREEN}  \u2551   FCT6 \u72EC\u7ACB\u90E8\u7F72\u811A\u672C          \u2551${NC}"
echo -e "${GREEN}  \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d${NC}"
echo ""

parse_args "$@"
preflight "$@"
detect_os
install_system_deps
create_dirs
setup_venv
setup_firewall
setup_systemd
start_service
show_complete
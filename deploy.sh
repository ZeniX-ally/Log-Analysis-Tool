#!/bin/bash
set -e

# ============================================================
# NEXUS FCT Dashboard - Linux 一键部署脚本
# ============================================================
# 支持: Ubuntu 20.04+, Debian 11+, CentOS 8+/RHEL/Rocky 9+
# 用法: 上传整个项目到服务器，然后:
#       chmod +x deploy.sh && sudo ./deploy.sh
#
# 功能:
#   1. 自动安装 Python3 + pip + venv
#   2. 创建虚拟环境并安装依赖
#   3. 创建 systemd 服务（开机自启 + 进程守护）
#   4. 配置防火墙（UFW / firewalld）
#   5. 可选: 配置 Nginx 反向代理 + SSL
#   6. 可选: 配置飞书 Webhook
#   7. 健康检查 + 显示管理命令
# ============================================================

# ---------- 颜色 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ---------- 配置变量 ----------
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SERVER_PORT=59488
VENV_DIR="$PROJECT_ROOT/venv"
SERVICE_NAME="nexus-fct.service"
NGINX_CONF_NAME="nexus-fct-nginx.conf"
LOG_DIR="/var/log/nexus-fct"
DATA_DIR="$PROJECT_ROOT/data"
DEPLOY_DIR="$PROJECT_ROOT/deploy"

# ---------- 打印函数 ----------
print_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_step()  { echo -e "\n${BLUE}══════════════════════════════════${NC}"; echo -e "${BLUE}  $1${NC}"; echo -e "${BLUE}══════════════════════════════════${NC}"; }
print_ok()    { echo -e "${GREEN}  ✓ $1${NC}"; }
print_ask()   { echo -e "${CYAN}  ? $1${NC}"; }

# ---------- 0. 前置检查 ----------
preflight() {
    print_step "前置检查"

    # 必须 root / sudo
    if [ "$EUID" -ne 0 ]; then
        if command -v sudo &> /dev/null; then
            print_warn "需要 root 权限，自动通过 sudo 重新执行..."
            exec sudo bash "$0" "$@"
            exit 0
        fi
        print_error "请以 root 或 sudo 运行: sudo bash $0"
        exit 1
    fi

    # 检查目录结构
    if [ ! -f "$PROJECT_ROOT/backend/app.py" ]; then
        print_error "未找到 backend/app.py，请在项目根目录执行: cd /path/to/nexus-fct && sudo bash deploy.sh"
        exit 1
    fi
    if [ ! -d "$DEPLOY_DIR" ]; then
        print_warn "未找到 deploy/ 目录，创建..."
        mkdir -p "$DEPLOY_DIR"
    fi

    print_ok "项目路径: $PROJECT_ROOT"
    print_ok "部署版本: $(date +%Y%m%d)"
}

# ---------- 1. 检测 OS ----------
detect_os() {
    print_step "检测操作系统"

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
        print_ok "发行版: $OS $OS_VERSION"
    else
        print_error "无法检测系统发行版"
        exit 1
    fi

    # 检查 Python3
    if command -v python3 &> /dev/null; then
        PY_VER=$(python3 --version 2>&1)
        print_ok "Python: $PY_VER"
    else
        print_warn "未安装 Python3，将在下一步安装"
    fi
}

# ---------- 2. 安装系统依赖 ----------
install_system_deps() {
    print_step "安装系统依赖"

    case $OS in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip python3-venv git curl ufw
            ;;
        centos|rhel|rocky|almalinux|fedora)
            if command -v dnf &> /dev/null; then
                dnf install -y -q python3 python3-pip python3-venv git curl firewalld
            else
                yum install -y -q python3 python3-pip python3-venv git curl firewalld
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

    # 确保 pip 和 venv 可用
    python3 -m ensurepip --upgrade 2>/dev/null || true
    print_ok "系统依赖安装完成"
}

# ---------- 3. 创建数据目录 ----------
create_dirs() {
    print_step "创建运行目录"

    mkdir -p "$DATA_DIR/logs"
    mkdir -p "$PROJECT_ROOT/cache"
    mkdir -p "$LOG_DIR"

    # 权限
    chmod -R 755 "$DATA_DIR"
    chmod -R 755 "$PROJECT_ROOT/cache"
    chmod -R 755 "$LOG_DIR"

    print_ok "数据目录: $DATA_DIR/logs"
    print_ok "缓存目录: $PROJECT_ROOT/cache"
    print_ok "日志目录: $LOG_DIR"
}

# ---------- 4. 创建虚拟环境 ----------
setup_venv() {
    print_step "配置 Python 虚拟环境"

    if [ -d "$VENV_DIR" ]; then
        print_warn "虚拟环境已存在，跳过创建"
    else
        python3 -m venv "$VENV_DIR"
        print_ok "虚拟环境创建完成"
    fi

    source "$VENV_DIR/bin/activate"
    print_ok "虚拟环境已激活: $VENV_DIR"
}

# ---------- 5. 安装 Python 依赖 ----------
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
    print_ok "  - gunicorn (生产级 WSGI 服务器)"
    print_ok "  - rich (终端仪表盘)"
    print_ok "  - psutil (系统监控)"
}

# ---------- 6. 配置防火墙 ----------
setup_firewall() {
    print_step "配置防火墙 (端口 $SERVER_PORT)"

    if command -v ufw &> /dev/null; then
        ufw allow "$SERVER_PORT"/tcp > /dev/null 2>&1 || true
        if command -v ufw &> /dev/null && ufw status | grep -q inactive 2>/dev/null; then
            print_warn "UFW 未启用，跳过防火墙配置（不影响运行）"
            print_ask "如需启用: sudo ufw enable && sudo ufw allow ssh"
        else
            print_ok "UFW 已开放端口 $SERVER_PORT"
        fi
    elif command -v firewall-cmd &> /dev/null; then
        firewall-cmd --permanent --add-port="$SERVER_PORT"/tcp > /dev/null 2>&1 || true
        firewall-cmd --reload > /dev/null 2>&1 || true
        print_ok "firewalld 已开放端口 $SERVER_PORT"
    else
        print_warn "未检测到防火墙，端口 $SERVER_PORT 可能被云服务商安全组拦截"
        print_ask "请检查云服务商的安全组/防火墙设置"
    fi
}

# ---------- 7. 配置 Systemd 服务 ----------
setup_systemd() {
    print_step "配置 Systemd 服务 (开机自启 + 进程守护)"

    local SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

    # 使用 deploy/ 目录下的 service 模板
    if [ -f "$DEPLOY_DIR/$SERVICE_NAME" ]; then
        # 替换模板中的占位符
        sed -e "s|/opt/nexus-fct|$PROJECT_ROOT|g" \
            -e "s|User=nexus|User=$(logname 2>/dev/null || echo 'root')|g" \
            -e "s|Group=nexus|Group=$(logname 2>/dev/null || echo 'root')|g" \
            "$DEPLOY_DIR/$SERVICE_NAME" > /tmp/$SERVICE_NAME.tmp
        cp /tmp/$SERVICE_NAME.tmp "$SERVICE_PATH"
        rm -f /tmp/$SERVICE_NAME.tmp
    else
        # 模板不存在，即时生成
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
    fi

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME" > /dev/null 2>&1
    print_ok "Systemd 服务配置完成: $SERVICE_NAME"
}

# ---------- 8. 启动服务 ----------
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

# ---------- 9. 健康检查 ----------
health_check() {
    print_step "执行健康检查"

    local HEALTH_URL="http://127.0.0.1:$SERVER_PORT"

    for i in {1..5}; do
        if curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null | grep -q "200\|302"; then
            print_ok "HTTP 服务正常 (200)"
            print_ok "API 端点和飞书集成均已可用"
            break
        fi
        if [ $i -eq 5 ]; then
            print_warn "HTTP 检查超时，服务可能仍在初始化"
            print_ask "稍后运行: curl -I http://127.0.0.1:$SERVER_PORT"
        fi
        sleep 1
    done
}

# ---------- 10. 配置飞书 Webhook（可选）----------
setup_feishu() {
    print_step "配置飞书集成（可选）"

    local WEBHOOK_FILE="$DATA_DIR/feishu_webhook.json"

    # 如果已有配置，跳过
    if [ -f "$WEBHOOK_FILE" ] && [ -s "$WEBHOOK_FILE" ]; then
        local CURRENT_URL=$(python3 -c "import json; print(json.load(open('$WEBHOOK_FILE')).get('webhook_url',''))" 2>/dev/null)
        if [ -n "$CURRENT_URL" ]; then
            print_ok "飞书 Webhook 已配置 (${CURRENT_URL:0:40}...)"
            print_ask "如需修改，请编辑: $WEBHOOK_FILE"
            return
        fi
    fi

    echo ""
    print_ask "是否配置飞书群机器人 Webhook？(y/N)"
    read -r -t 10 FEISHU_CHOICE || FEISHU_CHOICE="n"

    if [ "$FEISHU_CHOICE" != "y" ] && [ "$FEISHU_CHOICE" != "Y" ]; then
        print_warn "跳过飞书配置，随时可通过页面 ⚙️ 齿轮图标配置"
        return
    fi

    echo -n "请输入飞书 Webhook URL: "
    read -r WEBHOOK_URL

    if [ -z "$WEBHOOK_URL" ]; then
        print_warn "未输入 URL，跳过配置"
        return
    fi

    cat > "$WEBHOOK_FILE" <<EOF
{
    "webhook_url": "$WEBHOOK_URL",
    "updated_at": "$(date '+%Y-%m-%d %H:%M:%S')"
}
EOF

    print_ok "飞书 Webhook 已保存"

    # 测试连接
    print_ask "是否测试飞书连接？(Y/n)"
    read -r -t 10 TEST_CHOICE || TEST_CHOICE="y"
    if [ "$TEST_CHOICE" != "n" ] && [ "$TEST_CHOICE" != "N" ]; then
        curl -s -X POST "$WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"msg_type\":\"text\",\"content\":{\"text\":\"🚀 NEXUS FCT 已成功部署到服务器！\"}}" \
            -o /dev/null -w "%{http_code}" 2>/dev/null | grep -q "200" && \
            print_ok "飞书测试消息已发送，请查看群聊！" || \
            print_warn "测试消息发送失败，请检查 URL 是否正确"
    fi
}

# ---------- 11. 配置 Nginx（可选）----------
setup_nginx() {
    print_step "配置 Nginx 反向代理（可选）"

    echo ""
    print_ask "是否安装并配置 Nginx 反向代理？(y/N)"
    read -r -t 10 NGINX_CHOICE || NGINX_CHOICE="n"

    if [ "$NGINX_CHOICE" != "y" ] && [ "$NGINX_CHOICE" != "Y" ]; then
        print_warn "跳过 Nginx 配置，直接使用 http://IP:$SERVER_PORT 访问"
        return
    fi

    # 安装 Nginx
    case $OS in
        ubuntu|debian)
            apt-get install -y -qq nginx
            ;;
        centos|rhel|rocky|almalinux|fedora)
            if command -v dnf &> /dev/null; then
                dnf install -y -q nginx
            else
                yum install -y -q nginx
            fi
            ;;
    esac

    print_ok "Nginx 安装完成"

    # 询问域名
    echo -n "请输入域名（留空则用 IP: $SERVER_PORT）: "
    read -r DOMAIN

    if [ -n "$DOMAIN" ]; then
        # 使用域名配置
        if [ -f "$DEPLOY_DIR/$NGINX_CONF_NAME" ]; then
            sed "s/YOUR_DOMAIN/$DOMAIN/g" "$DEPLOY_DIR/$NGINX_CONF_NAME" > /etc/nginx/sites-available/$NGINX_CONF_NAME
        else
            cat > /etc/nginx/sites-available/$NGINX_CONF_NAME <<NGINXEOF
server {
    listen 80;
    server_name $DOMAIN;
    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:$SERVER_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 120s;
    }

    location /static/ {
        alias $PROJECT_ROOT/frontend/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
NGINXEOF
        fi

        # 启用站点
        ln -sf /etc/nginx/sites-available/$NGINX_CONF_NAME /etc/nginx/sites-enabled/ 2>/dev/null || true
        rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

        # 测试 nginx 配置
        nginx -t 2>/dev/null && systemctl reload nginx && print_ok "Nginx 配置完成！"
        print_ok "访问地址: http://$DOMAIN"

        # 询问 SSL
        print_ask "是否用 Certbot 自动配置 SSL (HTTPS)？(y/N)"
        read -r -t 10 SSL_CHOICE || SSL_CHOICE="n"
        if [ "$SSL_CHOICE" = "y" ] || [ "$SSL_CHOICE" = "Y" ]; then
            if command -v certbot &> /dev/null; then
                certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "admin@$DOMAIN" 2>/dev/null || \
                certbot --nginx -d "$DOMAIN"
            else
                apt-get install -y -qq certbot python3-certbot-nginx 2>/dev/null || \
                dnf install -y -q certbot python3-certbot-nginx 2>/dev/null || true
                certbot --nginx -d "$DOMAIN"
            fi
            print_ok "HTTPS 已启用: https://$DOMAIN"
        fi
    else
        # 无域名，简单反向代理
        cat > /etc/nginx/sites-available/nexus-fct.conf <<NGINXEOF
server {
    listen 80;
    server_name _;
    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:$SERVER_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
NGINXEOF
        ln -sf /etc/nginx/sites-available/nexus-fct.conf /etc/nginx/sites-enabled/ 2>/dev/null || true
        nginx -t 2>/dev/null && systemctl reload nginx && print_ok "Nginx 已配置为 80 端口转发到 $SERVER_PORT"
        print_ok "访问地址: http://$(hostname -I | awk '{print $1}')"
    fi

    # 开放 80/443 端口
    if command -v ufw &> /dev/null; then
        ufw allow 80/tcp > /dev/null 2>&1 || true
        ufw allow 443/tcp > /dev/null 2>&1 || true
        print_ok "UFW 已开放 HTTP/HTTPS 端口"
    fi
}

# ---------- 12. 显示完成信息 ----------
show_complete() {
    local IP=$(hostname -I | awk '{print $1}')
    local DIRECT_URL="http://$IP:$SERVER_PORT"

    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  🚀 NEXUS FCT Dashboard 部署成功！${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo -e "  ${CYAN}项目路径:${NC}   $PROJECT_ROOT"
    echo -e "  ${CYAN}直接访问:${NC}   $DIRECT_URL"

    if [ -n "$DOMAIN" ]; then
        echo -e "  ${CYAN}域名访问:${NC}   http://$DOMAIN"
    fi

    echo ""
    echo -e "  ${BLUE}══════════ 服务管理 ══════════${NC}"
    echo -e "  启动/停止/重启/状态:"
    echo -e "    sudo systemctl start/stop/restart/status ${SERVICE_NAME%.*}"
    echo -e "  实时日志:"
    echo -e "    sudo journalctl -u ${SERVICE_NAME%.*} -f"
    echo -e "    sudo tail -f $LOG_DIR/access.log"
    echo ""
    echo -e "  ${BLUE}══════════ 飞书集成 ══════════${NC}"
    echo -e "  页面配置: $DIRECT_URL → ⚙️ 齿轮图标"
    echo -e "  手动配置: vim $DATA_DIR/feishu_webhook.json"
    echo -e "  触发日报: curl -X POST http://127.0.0.1:$SERVER_PORT/api/feishu/daily-report"
    echo ""
    echo -e "  ${BLUE}══════════ API 清单 ══════════${NC}"
    echo -e "  GET  /api/stats                 效能统计"
    echo -e "  GET  /api/recent                 最新日志"
    echo -e "  GET  /api/limit/compare          限值比对"
    echo -e "  GET  /api/alerts/risk            风险预警"
    echo -e "  GET  /api/feishu/webhook         查看飞书配置"
    echo -e "  PUT  /api/feishu/webhook         设置飞书配置"
    echo -e "  POST /api/feishu/test            测试飞书连接"
    echo -e "  POST /api/feishu/daily-report    触发日报"
    echo ""
    echo -e "  ${BLUE}══════════ 常见问题 ══════════${NC}"
    echo -e "  ❓ 无法访问页面 →  检查防火墙/云服务商安全组"
    echo -e "  ❓ 无法解析日志 →  sudo tail -f $LOG_DIR/error.log"
    echo -e "  ❓ 更换端口 → 修改 deploy.sh 的 SERVER_PORT 重新部署"
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo ""
}

# ============================================================
# 主程序
# ============================================================
clear
echo ""
echo -e "${GREEN}  ╔═══════════════════════════════════╗${NC}"
echo -e "${GREEN}  ║   NEXUS FCT Dashboard              ║${NC}"
echo -e "${GREEN}  ║   Linux 一键部署脚本               ║${NC}"
echo -e "${GREEN}  ╚═══════════════════════════════════╝${NC}"
echo ""

preflight
detect_os
install_system_deps
create_dirs
setup_venv
install_python_deps
setup_firewall
setup_systemd
start_service
health_check
setup_feishu
setup_nginx
show_complete

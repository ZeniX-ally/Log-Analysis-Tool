#!/bin/bash
# ==========================================
# NEXUS FCT Dashboard - Ubuntu 生产环境一键配置脚本
# ==========================================

# 1. 变量定义
SERVER_PORT=5000
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SERVICE_NAME="nexus-fct.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

echo "=========================================================="
echo " [中枢系统] 开始执行第五步：系统级权限与服务部署"
echo " 服务器 IP: 172.28.55.66"
echo " 工程路径: $PROJECT_ROOT"
echo "=========================================================="

# 2. 防火墙配置
echo "[1/4] 配置 UFW 防火墙..."
# [修改对比批注]
# 逻辑：显式开放 5000 端口，确保边缘机台（FCT 12/16）可跨网段推送 XML。
sudo ufw allow $SERVER_PORT/tcp > /dev/null
sudo ufw reload > /dev/null
echo "      ✅ 端口 $SERVER_PORT 已开放。"

# 3. 目录权限配置
echo "[2/4] 修正数据目录权限..."
# [修改对比批注]
# 原内容：Windows 下无需显式处理权限。
# 修改逻辑：Ubuntu 环境下必须赋予运行用户写权限，否则 app.py 无法生成 telemetry_cache.json。
if [ -d "$PROJECT_ROOT/data" ]; then
    sudo chown -R $USER:$USER "$PROJECT_ROOT/data"
    sudo chmod -R 755 "$PROJECT_ROOT/data"
    echo "      ✅ $PROJECT_ROOT/data 权限已修正为 755。"
else
    mkdir -p "$PROJECT_ROOT/data/logs"
    sudo chown -R $USER:$USER "$PROJECT_ROOT/data"
    echo "      ✅ 已自动创建 data 目录并初始化权限。"
fi

# 4. Systemd 服务挂载
echo "[3/4] 挂载守护进程服务..."
# [修改对比批注]
# 逻辑：将第一步生成的 service 文件正式链接至系统目录。
if [ -f "$PROJECT_ROOT/$SERVICE_NAME" ]; then
    sudo cp "$PROJECT_ROOT/$SERVICE_NAME" "$SERVICE_PATH"
    
    # 动态修正 Service 文件中的绝对路径与用户名（防御性适配）
    sudo sed -i "s|User=user_name|User=$USER|g" "$SERVICE_PATH"
    sudo sed -i "s|/path/to/Log-Analysis-Tool|$PROJECT_ROOT|g" "$SERVICE_PATH"
    
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME > /dev/null
    sudo systemctl restart $SERVICE_NAME
    echo "      ✅ $SERVICE_NAME 服务已启动并配置为开机自启。"
else
    echo "      ❌ 错误：未在根目录找到 $SERVICE_NAME，请检查第一步产物。"
    exit 1
fi

# 5. 最终联调校验
echo "[4/4] 执行服务健康检查..."
sleep 2
STATUS=$(systemctl is-active $SERVICE_NAME)
if [ "$STATUS" = "active" ]; then
    echo "=========================================================="
    echo " 🎉 部署成功！"
    echo " Dashboard 访问地址: http://172.28.55.66:5000"
    echo " 实时日志监控指令: sudo journalctl -u $SERVICE_NAME -f"
    echo "=========================================================="
else
    echo " ⚠️ 服务启动异常，请运行 'sudo journalctl -u $SERVICE_NAME -n 50' 查看报错细节。"
fi
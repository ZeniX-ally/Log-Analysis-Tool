@echo off
:: 设置 UTF-8 编码，防止中文在 CMD 窗口乱码
chcp 65001 >nul
title FCT Smart Monitor - 核心诊断终端
color 0A

echo.
echo    ███████╗ ██████╗████████╗    ███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗██████╗ ██████╗ 
echo    ██╔════╝██╔════╝╚══██╔══╝    ████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗
echo    █████╗  ██║        ██║       ██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝
echo    ██╔══╝  ██║        ██║       ██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗
echo    ██║     ╚██████╗   ██║       ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║
echo    ╚═╝      ╚═════╝   ╚═╝       ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
echo.                                                                                          
echo =========================================================================================
echo                    G4.9 产线物理链路与三态解析引擎 (Windows 10 适配版)
echo =========================================================================================
echo.

:: [1] 核心环境探针
echo [System] 正在探测底层 Python 引擎...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo.
    echo [FATAL ERROR] 严重错误：未检测到 Python 环境变量！
    echo --------------------------------------------------
    echo 补救措施：
    echo 1. 请确认该机台已安装 Python 3.8+
    echo 2. 重新运行安装程序，务必勾选底部的 "Add Python 3.x to PATH"
    echo 3. 或者手动将 Python 安装路径添加到 Windows 系统高级环境变量中。
    echo --------------------------------------------------
    pause
    exit /b
)

:: [2] 依赖静默修复
echo [System] 验证并挂载依赖库 (Flask, 引擎支撑)...
:: 使用清华源加速，>nul 屏蔽大面积滚屏日志，保持界面清爽
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1

:: [3] 环境变量与路径注入
echo [System] 正在挂载解析器路由...
set PYTHONPATH=%cd%
set FLASK_ENV=production

:: [4] 唤起前端 UI
echo [System] 打通本地 5000 端口，即将唤醒沉浸式交互面板...
:: 延迟 1 秒让端口准备好
timeout /t 1 /nobreak >nul
start "" "http://127.0.0.1:5000/"

:: [5] 引擎主进程点火
echo [System] 解析引擎点火，开始监听 data/logs 目录...
echo.
python backend\app.py

:: [6] 崩溃拦截锁
echo.
color 0C
echo [System Warning] 核心服务已中断或被强制关闭。
pause
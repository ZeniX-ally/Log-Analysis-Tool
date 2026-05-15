@echo off
chcp 65001 >nul
title NEXUS FCT - 本地测试环境
cd /d "%~dp0.."

echo ==========================================
echo   NEXUS FCT - Windows 本地测试启动
echo ==========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.8+
    echo        下载: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 安装依赖（跳过 gunicorn，仅 Windows 可用库）
echo [1/4] 安装 Python 依赖...
pip install flask rich psutil -q
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)
echo   OK

:: 生成测试数据
echo [2/4] 生成模拟测试数据...
python tools\generate_test_data.py 30
if %errorlevel% neq 0 (
    echo [警告] 测试数据生成异常，继续启动...
)
echo   OK

:: 启动服务器
echo [3/4] 启动 Flask 服务器 (端口 59488)...
echo.
echo ==========================================
echo   服务器启动中...
echo   浏览器打开: http://localhost:59488
echo   按 Ctrl+C 停止服务器
echo ==========================================
echo.

python backend\app.py

:: 如果服务器退出
echo.
echo [信息] 服务器已停止
pause
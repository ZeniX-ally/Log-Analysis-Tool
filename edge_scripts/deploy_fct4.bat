@echo off
chcp 65001 >nul
title FCT4 边缘代理一键部署 - 172.28.55.14
echo ================================================================
echo    PEU FCT Edge Agent - 一键部署脚本
echo    机台: FCT4 ^| IP: 172.28.55.14 ^| ID: PEU_G49_FCT4_01
echo ================================================================
echo.

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 请以管理员身份运行此脚本！
    pause
    exit /b 1
)

set "INSTALL_DIR=C:\FCTAgent"
set "MACHINE_ID=PEU_G49_FCT4_01"
set "MACHINE_IP=172.28.55.14"
set "LOG_DIR=D:\Results"
set "SERVER_IP=172.28.55.66"
set "SERVER_PORT=59488"
set "TASK_NAME=FCTAgent_FCT4"

echo [1/6] 创建安装目录 %INSTALL_DIR% ...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo [2/6] 写入 config.json ...
(
echo {
echo   "server_ip": "%SERVER_IP%",
echo   "server_port": "%SERVER_PORT%",
echo   "machine_id": "%MACHINE_ID%",
echo   "machine_ip": "%MACHINE_IP%",
echo   "log_dir": "%LOG_DIR%",
echo   "poll_interval": 5
echo }
) > "%INSTALL_DIR%\config.json"
echo      config.json 已生成

echo [3/6] 部署 fct_agent.py ...
copy /Y "%~dp0fct_agent.py" "%INSTALL_DIR%\fct_agent.py" >nul
if %errorLevel% equ 0 (
    echo      fct_agent.py 已复制
) else (
    echo [警告] 未找到 fct_agent.py，请确保与本脚本在同一目录
)

echo [4/6] 创建静默启动脚本 run_hidden.vbs ...
(
echo Set shell = CreateObject^("WScript.Shell"^)
echo shell.Run "python """ ^& "%INSTALL_DIR%\fct_agent.py" ^& """", 0, False
echo Set shell = Nothing
) > "%INSTALL_DIR%\run_hidden.vbs"
echo      run_hidden.vbs 已生成

echo [5/6] 配置开机自启（任务计划程序）...
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if %errorLevel% equ 0 (
    schtasks /delete /tn "%TASK_NAME%" /f >nul
)
schtasks /create /tn "%TASK_NAME%" /tr "wscript.exe \"%INSTALL_DIR%\run_hidden.vbs\"" /sc onlogon /rl highest /f >nul
if %errorLevel% equ 0 (
    echo      开机自启任务已创建: %TASK_NAME%
) else (
    echo [警告] 创建计划任务失败，请手动配置
)

echo [6/6] 启动边缘代理（静默模式）...
wscript.exe "%INSTALL_DIR%\run_hidden.vbs"
if %errorLevel% equ 0 (
    echo      代理已静默启动
) else (
    echo [警告] 启动失败，请手动运行: python "%INSTALL_DIR%\fct_agent.py"
)

echo.
echo ================================================================
echo  部署完成！
echo  机台: FCT4 (172.28.55.14)
echo  服务器: %SERVER_IP%:%SERVER_PORT%
echo  日志目录: %LOG_DIR%
echo  安装路径: %INSTALL_DIR%
echo  自启任务: %TASK_NAME%
echo ================================================================
echo.
echo  管理命令：
echo   - 查看状态: schtasks /query /tn "%TASK_NAME%"
echo   - 手动启动: wscript.exe "%INSTALL_DIR%\run_hidden.vbs"
echo   - 手动停止: taskkill /f /im python.exe 2^>nul
echo   - 卸载: schtasks /delete /tn "%TASK_NAME%" /f ^& rmdir /s /q "%INSTALL_DIR%"
echo.
pause
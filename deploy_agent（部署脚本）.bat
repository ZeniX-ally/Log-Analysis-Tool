@echo off
setlocal enabledelayedexpansion
color 0A

echo ========================================================
echo   FCT 边缘采集 Agent 自动化部署中枢 (Production)
echo   Target Server IP: 172.28.55.66
echo ========================================================
echo.

:: 1. 强制权限校验
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] 权限阻断：当前非管理员权限。
    echo 请关闭此窗口，右键点击 deploy_agent.bat，选择“以管理员身份运行”。
    pause
    exit /b
)

:: 2. 交互式获取机台标识
echo 请输入当前要部署的机台编号 (直接输入数字 1 到 6):
set /p FCT_ID="> "

if "%FCT_ID%"=="" goto invalid
if %FCT_ID% lss 1 goto invalid
if %FCT_ID% gtr 6 goto invalid

set MACHINE_NAME=PEU_G49_FCT%FCT_ID%_01
set SERVER_IP=172.28.55.66
set AGENT_DIR=D:\FTS\Agent

echo.
echo [1/4] 正在配置工程部署目录...
if not exist "%AGENT_DIR%" mkdir "%AGENT_DIR%"
:: 只确保目标日志盘存在，不做任何修改写入
if not exist "D:\Results" mkdir "D:\Results"

if not exist "fct_ipc_agent.py" (
    echo [!] 致命错误：当前目录下找不到 fct_ipc_agent.py 脚本。
    echo 请确保 bat 和 py 文件在同一目录下。
    pause
    exit /b
)

copy /Y "fct_ipc_agent.py" "%AGENT_DIR%\fct_ipc_agent.py" >nul

echo [2/4] 正在注入网络拓扑与机台身份 (%MACHINE_NAME%)...
python -c "import sys,re; f=sys.argv[1]; c=open(f,'r',encoding='utf-8').read(); c=c.replace('10.222.126.115', '%SERVER_IP%'); c=re.sub(r'MACHINE_ID\s*=\s*\x22[^\x22]*\x22', 'MACHINE_ID = \x22'+sys.argv[2]+'\x22', c); open(f,'w',encoding='utf-8').write(c)" "%AGENT_DIR%\fct_ipc_agent.py" "%MACHINE_NAME%"

echo [3/4] 正在注册底层开机自启系统服务...
schtasks /delete /tn "FCT_Telemetry_Agent" /f >nul 2>&1
schtasks /create /tn "FCT_Telemetry_Agent" /tr "pythonw.exe \"%AGENT_DIR%\fct_ipc_agent.py\"" /sc onstart /ru SYSTEM /rl HIGHEST /f

echo [4/4] 正在唤醒边缘机守护进程...
schtasks /run /tn "FCT_Telemetry_Agent"

echo.
echo ========================================================
echo [OK] 部署防线已建立！
echo 节点标识 : %MACHINE_NAME%
echo 通信中枢 : %SERVER_IP%
echo 扫描目录 : D:\Results (绝对只读，不修改机台任何文件)
echo 运行状态 : 已作为 SYSTEM 级后台服务运行，防误关，抗重启。
echo ========================================================
pause
exit /b

:invalid
echo [!] 输入不合法。工程环境已重置，按任意键退出。
pause
exit /b
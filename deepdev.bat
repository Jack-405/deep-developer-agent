@echo off
rem  ============================================================
rem  deepdev - Deep Developer Agent 启动脚本 (Windows CMD)
rem
rem  用法:  deepdev [--workspace <path>] [--verbose]
rem
rem  说明:
rem    - 使用本脚本所在目录下的 .venv 解释器, 因此可以在任意
rem      目录启动, 不受当前命令行工作目录影响
rem    - 通过设置 PYTHONPATH 指向项目根目录, 保证 `cli` 包在
rem      任意工作目录下都能被导入
rem    - 不切换进程工作目录, 从而保证 agent 的默认工作区为
rem      "启动时的当前终端目录"
rem  ============================================================

set "DEEPDEV_ROOT=%~dp0"
set "DEEPDEV_PY=%DEEPDEV_ROOT%.venv\Scripts\python.exe"

if not exist "%DEEPDEV_PY%" (
    echo [deepdev] 错误: 未找到虚拟环境解释器: "%DEEPDEV_PY%"
    echo [deepdev] 请先在项目根目录创建 .venv 并安装依赖:
    echo [deepdev]     cd "%DEEPDEV_ROOT%"
    echo [deepdev]     uv sync
    exit /b 1
)

rem 将项目根目录加入 PYTHONPATH, 使 cli 包可在任意目录被导入
set "PYTHONPATH=%DEEPDEV_ROOT%%PYTHONPATH:;=%"

"%DEEPDEV_PY%" -m cli %*
exit /b %ERRORLEVEL%

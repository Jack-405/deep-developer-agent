# ============================================================
#  deepdev - Deep Developer Agent 启动脚本 (Windows PowerShell)
#
#  用法:  deepdev [--workspace <path>] [--verbose]
#
#  说明:
#    - 使用本脚本所在目录下的 .venv 解释器, 因此可以在任意
#      目录启动, 不受当前命令行工作目录影响
#    - 通过设置 PYTHONPATH 指向项目根目录, 保证 `cli` 包在
#      任意工作目录下都能被导入
#    - 不切换进程工作目录, 从而保证 agent 的默认工作区为
#      "启动时的当前终端目录"
# ============================================================

$DEEPDEV_ROOT = $PSScriptRoot
$DEEPDEV_PY = Join-Path $DEEPDEV_ROOT ".venv\Scripts\python.exe"

if (-not (Test-Path $DEEPDEV_PY)) {
    Write-Host "[deepdev] 错误: 未找到虚拟环境解释器: $DEEPDEV_PY"
    Write-Host "[deepdev] 请先在项目根目录创建 .venv 并安装依赖:"
    Write-Host "[deepdev]     cd $DEEPDEV_ROOT"
    Write-Host "[deepdev]     uv sync"
    exit 1
}

# 将项目根目录加入 PYTHONPATH, 使 cli 包可在任意目录被导入
$env:PYTHONPATH = $DEEPDEV_ROOT + $(if ($env:PYTHONPATH) { ";" + $env:PYTHONPATH } else { "" })

& $DEEPDEV_PY -m cli @args
exit $LASTEXITCODE

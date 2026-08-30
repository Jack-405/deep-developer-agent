# 下载并安装 obsidian-mcp 预编译二进制（Windows x86_64）
# 用途：本机无 cargo 时，从 GitHub Releases 拉取预编译二进制，避免本地编译。
# 用法（项目根目录执行）：
#   powershell -ExecutionPolicy Bypass -File scripts\install-obsidian-mcp.ps1
#
# 安装位置：默认 vendor\obsidian-mcp（不进入 git，vendor/ 已被 .gitignore 排除）；
#           可用 -Destination <dir> 覆盖。
# 安装完成后把二进制路径写进 .env：
#   OBSIDIAN_BIN=<绝对路径>\obsidian-mcp.exe
#   OBSIDIAN_VAULT_PATH=<你的 Obsidian vault 目录>

param(
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"

$repo = "lstpsche/obsidian-mcp"

# 默认安装到 vendor\obsidian-mcp（项目根 = 本脚本上级目录）
if (-not $Destination) {
    $Destination = Join-Path (Split-Path -Parent $PSScriptRoot) "vendor\obsidian-mcp"
}

Write-Host "Fetching latest release info from $repo ..."
$rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest"
$asset = $rel.assets | Where-Object { $_.name -match "x86_64-pc-windows-msvc\.zip$" } | Select-Object -First 1
if (-not $asset) { throw "No Windows x86_64 zip asset found in latest release" }

$zip = Join-Path $env:TEMP $asset.name
Write-Host "Downloading $($asset.name) ($([math]::Round($asset.size / 1MB, 1)) MB) ..."
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
Write-Host "Extracting to $Destination ..."
Expand-Archive -Path $zip -DestinationPath $Destination -Force
Remove-Item $zip -Force

$exe = Get-ChildItem -Path $Destination -Recurse -Filter "obsidian-mcp.exe" | Select-Object -First 1
if (-not $exe) { throw "obsidian-mcp.exe not found after extraction" }

Write-Host ""
Write-Host "Installed: $($exe.FullName)"
Write-Host "Version:   $(& $exe.FullName --version)"
Write-Host ""
Write-Host "Add to .env:"
Write-Host "  OBSIDIAN_BIN=$($exe.FullName)"
Write-Host "  OBSIDIAN_VAULT_PATH=<your vault path>"

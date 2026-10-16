$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = "$PSScriptRoot\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "$PSScriptRoot\..\.venv313\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw '请先按 README 创建项目虚拟环境并安装依赖。'
}
& $python "$PSScriptRoot\main.py"

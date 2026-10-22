param(
    [ValidateSet("prepare", "start", "status", "stop", "smoke")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Distro = "Ubuntu"
$LinuxUser = "duyan"

$wslWorkspace = (& wsl -d $Distro -u $LinuxUser -e wslpath -a "$Workspace").Trim()
$script = "$wslWorkspace/scripts/native_runtime/native_runtime.sh"

switch ($Action) {
    "smoke" {
        $python = Join-Path $Workspace ".venv-mcp-validation\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $python)) {
            throw "Missing existing validation venv interpreter: $python"
        }
        $evidenceDir = Join-Path $Workspace "docs\project\handoffs\OC-041\evidence"
        New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
        $output = Join-Path $evidenceDir "native_smoke.json"

        Write-Output "Windows host loopback check:"
        $tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 17687 -WarningAction SilentlyContinue
        Write-Output ("  TcpTestSucceeded={0}" -f $tcp.TcpTestSucceeded)
        if (-not $tcp.TcpTestSucceeded) {
            throw "Windows host cannot reach 127.0.0.1:17687"
        }

        & $python (Join-Path $Workspace "scripts\native_runtime\smoke_probe.py") --output $output
        if ($LASTEXITCODE -ne 0) {
            throw "Smoke probe failed with exit code $LASTEXITCODE"
        }
        Write-Output "Evidence written: $output"
    }
    default {
        & wsl -d $Distro -u $LinuxUser -e bash $script $Action
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
}

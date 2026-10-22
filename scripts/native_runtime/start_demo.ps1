#Requires -Version 5.1
<#
    START154 - Windows demo launcher for the POI MCP + AI services.

    Contract:
      * Resolve the repository root from $PSScriptRoot (no cd dependence).
      * Start cached engines only when both ports are closed; prove graph data
        and routing profiles before starting AI/MCP. Fail closed otherwise.
      * Reuse a healthy owned stack; never start a duplicate; never stop,
        restart or repair a degraded / foreign / unowned service.
      * Call the existing launcher (core_service.py) for status/start only.
      * Open the travel UI in the default browser only after every check passed.

    This script never reads secrets, installs, downloads or rebuilds data and
    never changes configuration. When both engine ports are closed it can start
    the cached engines through the prepared WSL Ubuntu runtime; missing or
    changed caches stay fail closed.
#>
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$NoPause
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
}

$EngineMissingMessage = 'DỪNG: Không khởi động được engine. Cần Memgraph (bolt://127.0.0.1:17687) và GraphHopper (http://127.0.0.1:18989) chạy với dữ liệu sẵn có. Khi cả hai cổng đang tắt, BAT khởi động lại từ cache/binary đã chuẩn bị và cần WSL Ubuntu/runtime đã cài sẵn; bản demo không tự cài đặt, không tải, không dựng lại dữ liệu và không sửa cấu hình. Nếu cache thiếu/hỏng hoặc trạng thái không đầy đủ thì dừng an toàn.'

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Python = Join-Path $Root '.venv-mcp-validation\Scripts\python.exe'
$CoreService = Join-Path $Root 'scripts\native_runtime\core_service.py'
$UiUrl = 'http://127.0.0.1:19102/travel'
$AiHealthUrl = 'http://127.0.0.1:19102/healthz'
$GraphHopperInfoUrl = 'http://127.0.0.1:18989/info'
$ModelAlias = 'opencode-go/deepseek-v4.1-flash'

# Read-only graph proof. The installed neo4j driver is used with auth None.
$GraphProbeCode = @'
QUERY = "MATCH (n:POI) RETURN count(n) AS poi_count"
try:
    from neo4j import GraphDatabase, Query
except Exception as exc:
    print("PROBE_IMPORT_FAILED " + type(exc).__name__)
    raise SystemExit(2)
try:
    driver = GraphDatabase.driver("bolt://127.0.0.1:17687", auth=None,
                                  connection_acquisition_timeout=3.0,
                                  max_transaction_retry_time=3.0)
    try:
        with driver.session(default_access_mode="READ") as session:
            record = session.run(Query(QUERY, timeout=5)).single()
            count = int(record["poi_count"]) if record is not None else -1
    finally:
        driver.close()
except Exception as exc:
    print("PROBE_FAILED " + type(exc).__name__)
    raise SystemExit(3)
if count <= 0:
    print("PROBE_EMPTY " + str(count))
    raise SystemExit(4)
print("PROBE_OK " + str(count))
'@

function Write-Step {
    param([string]$Text)
    Write-Host "[START154] $Text"
}

function Stop-Demo {
    param(
        [string]$Message,
        [int]$Code = 1
    )
    Write-Host ''
    Write-Host $Message -ForegroundColor Red
    exit $Code
}

function Get-Prop {
    param(
        $Object,
        [string]$Name
    )
    if ($null -eq $Object) {
        return $null
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Invoke-GraphProbe {
    $output = @()
    try {
        $output = $GraphProbeCode | & $Python '-' 2>&1
        $code = $LASTEXITCODE
    }
    catch {
        return [pscustomobject]@{ Ok = $false; Detail = 'probe_launch_failed' }
    }
    $text = (@($output) | ForEach-Object { [string]$_ }) -join ' '
    $text = $text.Trim()
    if ($code -ne 0) {
        return [pscustomobject]@{ Ok = $false; Detail = $text }
    }
    if ($text -notmatch 'PROBE_OK\s+(\d+)') {
        return [pscustomobject]@{ Ok = $false; Detail = $text }
    }
    $count = [int]$Matches[1]
    if ($count -le 0) {
        return [pscustomobject]@{ Ok = $false; Detail = 'empty_result' }
    }
    return [pscustomobject]@{ Ok = $true; Detail = ('POI count=' + $count) }
}

function Invoke-GraphHopperProbe {
    try {
        $info = Invoke-RestMethod -Uri $GraphHopperInfoUrl -Method Get `
            -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    }
    catch {
        return [pscustomobject]@{ Ok = $false; Detail = 'info_unreachable' }
    }
    $names = @()
    foreach ($item in @(Get-Prop $info 'profiles')) {
        $name = $null
        if ($item -is [string]) {
            $name = $item
        }
        else {
            $name = Get-Prop $item 'name'
        }
        if ($null -ne $name) {
            $names += [string]$name
        }
    }
    $hasCar = $false
    $hasFoot = $false
    foreach ($name in $names) {
        if ($name -eq 'car') { $hasCar = $true }
        if ($name -eq 'foot') { $hasFoot = $true }
    }
    if (-not ($hasCar -and $hasFoot)) {
        return [pscustomobject]@{ Ok = $false; Detail = ('profiles=' + ($names -join ',')) }
    }
    return [pscustomobject]@{ Ok = $true; Detail = 'profiles=car,foot' }
}

function Invoke-CoreStatus {
    $output = @()
    try {
        $output = & $Python $CoreService 'status' 2>$null
        $code = $LASTEXITCODE
    }
    catch {
        return [pscustomobject]@{ ExitCode = -1; Json = $null; Raw = $_.Exception.Message }
    }
    $text = (@($output) | ForEach-Object { [string]$_ }) -join "`n"
    $json = $null
    try {
        $json = $text | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        $json = $null
    }
    return [pscustomobject]@{ ExitCode = $code; Json = $json; Raw = $text }
}

function Test-DemoPortsFree {
    param([int[]]$Ports)
    # Complete enumeration: a non-terminating per-port lookup cannot prove
    # absence, so any enumeration failure counts as "not free".
    try {
        $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop)
    }
    catch {
        return $false
    }
    foreach ($listener in $listeners) {
        if ($Ports -contains [int]$listener.LocalPort) {
            return $false
        }
    }
    return $true
}

function Test-StaleStackRestartable {
    param($StatusJson)
    # Only the exact recorded pair, both proven gone, with both demo ports
    # free, may be restarted through the existing launcher.
    $services = Get-Prop $StatusJson 'services'
    if ($null -eq $services) {
        return $false
    }
    $names = @($services.PSObject.Properties | ForEach-Object { $_.Name })
    if ($names.Count -ne 2 -or -not ($names -contains 'mcp') -or -not ($names -contains 'ai')) {
        return $false
    }
    foreach ($name in @('mcp', 'ai')) {
        $record = Get-Prop $services $name
        if ($null -eq $record) {
            return $false
        }
        if ((Get-Prop $record 'owned') -ne $false) {
            return $false
        }
        if ([string](Get-Prop $record 'reason') -ne 'process_gone') {
            return $false
        }
    }
    return (Test-DemoPortsFree -Ports @(19101, 19102))
}

Write-Host 'START154 - Bản demo Travel/POI (Windows)'
Write-Step ('Thư mục dự án: ' + $Root)

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    Stop-Demo 'DỪNG: Không tìm thấy runtime Python đã cài của dự án (.venv-mcp-validation\Scripts\python.exe). Bản demo không tự cài đặt hay khôi phục runtime.'
}
if (-not (Test-Path -LiteralPath $CoreService -PathType Leaf)) {
    Stop-Demo 'DỪNG: Không tìm thấy scripts\native_runtime\core_service.py trong dự án.'
}

Write-Step 'Bước 1/4: Kiểm tra engine đang chạy (Memgraph, GraphHopper)...'
if (Test-DemoPortsFree -Ports @(17687, 18989)) {
    Write-Step '  Cả hai cổng engine đang tắt: khởi động lại từ cache/binary đã chuẩn bị...'
    $engineHelper = Join-Path $Root 'scripts/native_runtime/start_cached_engines.py'
    $engineExit = -1
    try {
        $null = & $Python $engineHelper 2>$null
        $engineExit = $LASTEXITCODE
    }
    catch {
        $engineExit = -1
    }
    if ($engineExit -ne 0) {
        Stop-Demo 'DỪNG: Không khởi động được engine từ cache đã chuẩn bị. Không thử lại, không tải và không cài đặt. Kiểm tra WSL Ubuntu/runtime và cache engine đã chuẩn bị, rồi chạy lại demo.'
    }
}
$graph = Invoke-GraphProbe
if (-not $graph.Ok) {
    Stop-Demo ($EngineMissingMessage + "`nChi tiết Memgraph: " + $graph.Detail)
}
Write-Step ('  Memgraph OK - ' + $graph.Detail + ' (truy vấn chỉ đọc)')

$hopper = Invoke-GraphHopperProbe
if (-not $hopper.Ok) {
    Stop-Demo ($EngineMissingMessage + "`nChi tiết GraphHopper: " + $hopper.Detail)
}
Write-Step ('  GraphHopper OK - ' + $hopper.Detail)

Write-Step 'Bước 2/4: Kiểm tra dịch vụ hiện có...'
$status = Invoke-CoreStatus
if ($null -eq $status.Json) {
    Stop-Demo ('DỪNG: Không đọc được trạng thái dịch vụ (core_service status, mã ' + $status.ExitCode + '). Không tự khởi động để tránh tạo tiến trình trùng lặp.' + "`n" + $status.Raw)
}

$state = [string](Get-Prop $status.Json 'status')
$needStart = $false
switch ($state) {
    'not_started' {
        $needStart = $true
        Write-Step '  Chưa có dịch vụ nào đang chạy.'
    }
    'running' {
        $services = Get-Prop $status.Json 'services'
        $mcp = Get-Prop $services 'mcp'
        $ai = Get-Prop $services 'ai'
        $mcpHealth = Get-Prop $mcp 'health'
        $aiHealth = Get-Prop $ai 'health'
        $mcpOk = ((Get-Prop $mcp 'owned') -eq $true) -and ((Get-Prop $mcpHealth 'ok') -eq $true)
        $aiOk = ((Get-Prop $ai 'owned') -eq $true) -and ((Get-Prop $aiHealth 'ok') -eq $true)
        if ($mcpOk -and $aiOk) {
            Write-Step '  Dịch vụ đang chạy sẵn và khỏe mạnh: dùng lại, không khởi động thêm.'
        }
        else {
            Stop-Demo 'DỪNG: Dịch vụ đang chạy nhưng chưa xác nhận đủ quyền sở hữu và health của cả MCP lẫn AI. Không dừng, không khởi động lại. Khi thuận tiện, dừng bằng ".venv-mcp-validation\Scripts\python.exe scripts\native_runtime\core_service.py stop" rồi mở lại demo.'
        }
    }
    'degraded' {
        if (Test-StaleStackRestartable -StatusJson $status.Json) {
            $needStart = $true
            Write-Step '  Dịch vụ lần chạy trước đã dừng (process_gone) và cổng 19101/19102 đang trống: khởi động lại bằng launcher.'
        }
        else {
            Stop-Demo 'DỪNG: Dịch vụ đang ở trạng thái degraded (có tiến trình lạ, health lỗi hoặc trạng thái không chứng minh được là đã dừng sạch). Không tự dừng và không khởi động lại để tránh ảnh hưởng tiến trình khác. Hãy xem log trong .runtime-native, xử lý nguyên nhân rồi chạy lại demo.'
        }
    }
    default {
        Stop-Demo ('DỪNG: Trạng thái dịch vụ không xác định ("' + $state + '"). Không tự khởi động.' + "`n" + $status.Raw)
    }
}

if ($needStart) {
    Write-Step ('Bước 3/4: Khởi động dịch vụ với model alias ' + $ModelAlias + '...')
    $output = @()
    try {
        $output = & $Python $CoreService 'start' '--alias' $ModelAlias 2>$null
        $startExit = $LASTEXITCODE
    }
    catch {
        $startExit = -1
        $output = @($_.Exception.Message)
    }
    $startText = (@($output) | ForEach-Object { [string]$_ }) -join "`n"
    if ($startExit -ne 0) {
        $startJson = $null
        try {
            $startJson = $startText | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            $startJson = $null
        }
        $errorCode = [string](Get-Prop $startJson 'error')
        Stop-Demo ('DỪNG: Khởi động dịch vụ thất bại (mã ' + $startExit + ', lỗi: ' + $errorCode + '). Không thử lại tự động.' + "`n" + $startText)
    }
}
else {
    Write-Step 'Bước 3/4: Bỏ qua khởi động (dịch vụ đã sẵn sàng).'
}

Write-Step 'Bước 4/4: Xác nhận lại status, health AI và MCP...'
$final = Invoke-CoreStatus
if ($null -eq $final.Json -or [string](Get-Prop $final.Json 'status') -ne 'running') {
    Stop-Demo 'DỪNG: Sau khi khởi động, trạng thái dịch vụ chưa phải "running". Không mở trình duyệt.'
}

$finalServices = Get-Prop $final.Json 'services'
$finalMcp = Get-Prop $finalServices 'mcp'
$finalAi = Get-Prop $finalServices 'ai'
$finalMcpHealth = Get-Prop $finalMcp 'health'
$finalAiHealth = Get-Prop $finalAi 'health'
$mcpReady = ((Get-Prop $finalMcp 'owned') -eq $true) -and ((Get-Prop $finalMcpHealth 'ok') -eq $true)
$aiReady = ((Get-Prop $finalAi 'owned') -eq $true) -and ((Get-Prop $finalAiHealth 'ok') -eq $true)
if (-not ($mcpReady -and $aiReady)) {
    Stop-Demo 'DỪNG: Launcher chưa xác nhận đủ quyền sở hữu và health cho cả MCP lẫn AI. Không mở trình duyệt.'
}

try {
    $aiHealth = Invoke-RestMethod -Uri $AiHealthUrl -Method Get `
        -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
}
catch {
    Stop-Demo 'DỪNG: Không gọi được /healthz của AI service. Không mở trình duyệt.'
}
if ([string](Get-Prop $aiHealth 'status') -ne 'ok' -or [string](Get-Prop $aiHealth 'service') -ne 'ai_service') {
    Stop-Demo 'DỪNG: AI service trả health không hợp lệ. Không mở trình duyệt.'
}
Write-Step '  Cả MCP và AI đều do launcher sở hữu và health OK.'

if ($NoBrowser) {
    Write-Step 'Bỏ qua mở trình duyệt theo -NoBrowser.'
}
else {
    Start-Process -FilePath $UiUrl
}

Write-Host ''
Write-Host ('SẴN SÀNG: ' + $UiUrl) -ForegroundColor Green
Write-Step 'Dừng dịch vụ khi cần: .venv-mcp-validation\Scripts\python.exe scripts\native_runtime\core_service.py stop'
exit 0

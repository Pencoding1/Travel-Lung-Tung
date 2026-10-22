$ErrorActionPreference = "Stop"

$Root = "E:\Project\TVLT_2026"
$State = Join-Path $Root ".runtime-native\graphhopper-11.1\state"
$Base = "http://127.0.0.1:18989"
$MaxTime = 120

function Get-Sha256([string]$Path) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $fs = [System.IO.File]::OpenRead($Path)
    try {
        $bytes = $sha.ComputeHash($fs)
        return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
    } finally {
        $fs.Dispose()
        $sha.Dispose()
    }
}

function Get-Haversine([double]$Lat1, [double]$Lon1, [double]$Lat2, [double]$Lon2) {
    $R = 6371000.0
    $dLat = ($Lat2 - $Lat1) * [Math]::PI / 180.0
    $dLon = ($Lon2 - $Lon1) * [Math]::PI / 180.0
    $a = [Math]::Sin($dLat / 2) * [Math]::Sin($dLat / 2) +
         [Math]::Cos($Lat1 * [Math]::PI / 180.0) * [Math]::Cos($Lat2 * [Math]::PI / 180.0) *
         [Math]::Sin($dLon / 2) * [Math]::Sin($dLon / 2)
    $c = 2 * [Math]::Atan2([Math]::Sqrt($a), [Math]::Sqrt(1 - $a))
    return $R * $c
}

$Pairs = @(
    @{ Name = "tan-son-nhat-to-ben-thanh"; FromLat = 10.8116; FromLon = 106.6611; ToLat = 10.7725; ToLon = 106.6980 },
    @{ Name = "city-hall-to-binh-tay"; FromLat = 10.7769; FromLon = 106.7009; ToLat = 10.7524; ToLon = 106.6505 }
)

$Results = @()
$Failures = 0

foreach ($Profile in @("car", "foot")) {
    foreach ($Pair in $Pairs) {
        $Point1 = "{0},{1}" -f $Pair.FromLat, $Pair.FromLon
        $Point2 = "{0},{1}" -f $Pair.ToLat, $Pair.ToLon
        $ChParam = if ($Profile -eq "foot") { "&ch.disable=true" } else { "" }
        $Query = "point=$Point1&point=$Point2&profile=$Profile&points_encoded=false&instructions=true&locale=en$ChParam"
        $Url = "$Base/route?$Query"
        $OutFile = Join-Path $State ("route-" + $Profile + "-" + $Pair.Name + ".json")
        $RequestedAt = [DateTimeOffset]::Now.ToString("o")

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $Http = (& curl.exe -sS --max-time $MaxTime -o $OutFile -w "%{http_code}" $Url)
        $sw.Stop()

        $Item = [ordered]@{
            profile = $Profile
            pair = $Pair.Name
            request_url = $Url
            requested_at = $RequestedAt
            http_status = $Http
            elapsed_ms = $sw.ElapsedMilliseconds
            response_file = $OutFile
            response_sha256 = $null
            distance_m = $null
            time_ms = $null
            point_count = $null
            snapped_start = $null
            snapped_end = $null
            snap_start_offset_m = $null
            snap_end_offset_m = $null
            straight_line_m = $null
            route_to_straight_ratio = $null
            finite_nonnegative = $false
            nonzero_road_route = $false
            pass = $false
            error = $null
        }

        if (Test-Path $OutFile) {
            $Item.response_sha256 = Get-Sha256 $OutFile
        }

        try {
            if ($Http -ne "200") { throw "unexpected HTTP status $Http" }
            $Data = Get-Content -LiteralPath $OutFile -Raw | ConvertFrom-Json
            if (-not $Data.paths -or $Data.paths.Count -lt 1) { throw "response has no paths" }
            $Path0 = $Data.paths[0]
            $Coords = $Path0.points.coordinates
            $Snapped = $Path0.snapped_waypoints.coordinates

            $Item.distance_m = [double]$Path0.distance
            $Item.time_ms = [double]$Path0.time
            $Item.point_count = $Coords.Count
            if ($Snapped -and $Snapped.Count -ge 2) {
                $Item.snapped_start = $Snapped[0]
                $Item.snapped_end = $Snapped[$Snapped.Count - 1]
                $Item.snap_start_offset_m = Get-Haversine $Pair.FromLat $Pair.FromLon $Snapped[0][1] $Snapped[0][0]
                $Item.snap_end_offset_m = Get-Haversine $Pair.ToLat $Pair.ToLon $Snapped[$Snapped.Count - 1][1] $Snapped[$Snapped.Count - 1][0]
            }

            $Item.straight_line_m = Get-Haversine $Pair.FromLat $Pair.FromLon $Pair.ToLat $Pair.ToLon
            if ($Item.straight_line_m -gt 0) {
                $Item.route_to_straight_ratio = $Item.distance_m / $Item.straight_line_m
            }

            $Item.finite_nonnegative = ([double]::IsNaN($Item.distance_m) -eq $false) -and
                ([double]::IsInfinity($Item.distance_m) -eq $false) -and
                ([double]::IsNaN($Item.time_ms) -eq $false) -and
                ([double]::IsInfinity($Item.time_ms) -eq $false) -and
                ($Item.distance_m -ge 0) -and ($Item.time_ms -ge 0)

            $Item.nonzero_road_route = ($Item.distance_m -gt 100) -and
                ($Item.time_ms -gt 0) -and
                ($Item.point_count -gt 10) -and
                ($Item.snap_start_offset_m -lt 500) -and
                ($Item.snap_end_offset_m -lt 500)

            $Item.pass = $Item.finite_nonnegative -and $Item.nonzero_road_route
        } catch {
            $Item.error = $_.Exception.Message
        }

        if (-not $Item.pass) { $Failures++ }
        $Results += [pscustomobject]$Item
        $Item | ConvertTo-Json -Depth 6
    }
}

$HealthW = & curl.exe -sS --max-time 10 -o (Join-Path $State "health-windows.txt") -w "%{http_code}" "$Base/health"
$InfoHealthW = & curl.exe -sS --max-time 10 -o (Join-Path $State "info-health-windows.txt") -w "%{http_code}" "$Base/info/health"
$AdminHealthW = & curl.exe -sS --max-time 10 -o (Join-Path $State "admin-health-windows.txt") -w "%{http_code}" "http://127.0.0.1:18990/healthcheck"
$Info = Get-Content -LiteralPath (Join-Path $State "info-windows.json") -Raw | ConvertFrom-Json

$Summary = [ordered]@{
    generated_at = [DateTimeOffset]::Now.ToString("o")
    base_url = $Base
    route_requests = $Results.Count
    route_failures = $Failures
    health_http = $HealthW
    info_health_http = $InfoHealthW
    admin_healthcheck_http = $AdminHealthW
    engine_version = $Info.version
    profiles = $Info.profiles.name
    elevation = $Info.elevation
    import_date = $Info.import_date
    data_date = $Info.data_date
    results = $Results
}

$Summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $State "routes-summary.json") -Encoding UTF8

"SUMMARY"
Get-Content -LiteralPath (Join-Path $State "routes-summary.json") -Raw
if ($Failures -ne 0) { exit 1 }

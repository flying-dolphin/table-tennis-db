param(
    [Parameter(Mandatory = $true)]
    [string]$ServerHost,

    [string]$RemoteOpsDir = "/opt/ittf-ops"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

$files = @(
    @{
        Local  = (Join-Path $RepoRoot "deploy\server\event_refresh.sh")
        Remote = "$RemoteOpsDir/event_refresh.sh"
    },
    @{
        Local  = (Join-Path $RepoRoot "deploy\server\cron_event_refresh_with_sentry.sh.example")
        Remote = "$RemoteOpsDir/cron_event_refresh_with_sentry.sh.example"
    },
    @{
        Local  = (Join-Path $RepoRoot "deploy\server\runtime\README.md")
        Remote = "$RemoteOpsDir/runtime/README.md"
    },
    @{
        Local  = (Join-Path $RepoRoot "deploy\server\runtime\data\stage_round_mapping.json")
        Remote = "$RemoteOpsDir/runtime/data/stage_round_mapping.json"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\backfill_events_calendar_event_id.py")
        Remote = "$RemoteOpsDir/runtime/python/backfill_events_calendar_event_id.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\import_session_schedule.py")
        Remote = "$RemoteOpsDir/runtime/python/import_session_schedule.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\import_wtt_event.py")
        Remote = "$RemoteOpsDir/runtime/python/import_wtt_event.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\event_refresh.py")
        Remote = "$RemoteOpsDir/runtime/python/event_refresh.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\scrape_wtt_event.py")
        Remote = "$RemoteOpsDir/runtime/python/scrape_wtt_event.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\scrape_wtt_pool_standings.py")
        Remote = "$RemoteOpsDir/runtime/python/scrape_wtt_pool_standings.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\import_wtt_pool_standings.py")
        Remote = "$RemoteOpsDir/runtime/python/import_wtt_pool_standings.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\lib\browser_runtime.py")
        Remote = "$RemoteOpsDir/runtime/python/lib/browser_runtime.py"
    }
)

Write-Host "Creating remote directories on $ServerHost ..."
& ssh $ServerHost "mkdir -p '$RemoteOpsDir' '$RemoteOpsDir/runtime' '$RemoteOpsDir/runtime/data' '$RemoteOpsDir/runtime/python' '$RemoteOpsDir/runtime/python/lib'"

foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath $file.Local)) {
        throw "Local file not found: $($file.Local)"
    }

    Write-Host "Uploading $($file.Local) -> $($file.Remote)"
    & scp $file.Local ("{0}:{1}" -f $ServerHost, $file.Remote)
}

Write-Host "Marking shell scripts as executable ..."
& ssh $ServerHost "chmod +x '$RemoteOpsDir/event_refresh.sh'"

Write-Host "Upload complete."

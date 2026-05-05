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
        Local  = (Join-Path $RepoRoot "deploy\server\install_current_event_crontab.sh")
        Remote = "$RemoteOpsDir/install_current_event_crontab.sh"
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
        Local  = (Join-Path $RepoRoot "scripts\runtime\generate_current_event_crontab.py")
        Remote = "$RemoteOpsDir/runtime/python/generate_current_event_crontab.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\import_current_event.py")
        Remote = "$RemoteOpsDir/runtime/python/import_current_event.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\import_current_event_brackets.py")
        Remote = "$RemoteOpsDir/runtime/python/import_current_event_brackets.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\import_current_event_completed.py")
        Remote = "$RemoteOpsDir/runtime/python/import_current_event_completed.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\import_current_event_group_standings.py")
        Remote = "$RemoteOpsDir/runtime/python/import_current_event_group_standings.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\import_current_event_live.py")
        Remote = "$RemoteOpsDir/runtime/python/import_current_event_live.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\import_current_event_session_schedule.py")
        Remote = "$RemoteOpsDir/runtime/python/import_current_event_session_schedule.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\scrape_current_event.py")
        Remote = "$RemoteOpsDir/runtime/python/scrape_current_event.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\scrape_wtt_brackets.py")
        Remote = "$RemoteOpsDir/runtime/python/scrape_wtt_brackets.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\scrape_wtt_live_matches.py")
        Remote = "$RemoteOpsDir/runtime/python/scrape_wtt_live_matches.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\scrape_wtt_matches.py")
        Remote = "$RemoteOpsDir/runtime/python/scrape_wtt_matches.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\scrape_wtt_pool_standings.py")
        Remote = "$RemoteOpsDir/runtime/python/scrape_wtt_pool_standings.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\scrape_wtt_schedule.py")
        Remote = "$RemoteOpsDir/runtime/python/scrape_wtt_schedule.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\wtt_import_shared.py")
        Remote = "$RemoteOpsDir/runtime/python/wtt_import_shared.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\wtt_scrape_shared.py")
        Remote = "$RemoteOpsDir/runtime/python/wtt_scrape_shared.py"
    },
    @{
        Local  = (Join-Path $RepoRoot "scripts\runtime\lib\browser_runtime.py")
        Remote = "$RemoteOpsDir/runtime/python/lib/browser_runtime.py"
    }
)

$StagingDir = Join-Path $PSScriptRoot "upload_staging"
$ArchiveName = "runtime_bundle.tar.gz"
$ArchivePath = Join-Path $PSScriptRoot $ArchiveName

Write-Host "Staging files locally..."
if (Test-Path $StagingDir) { Remove-Item -Recurse -Force $StagingDir }
New-Item -ItemType Directory -Path $StagingDir | Out-Null

foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath $file.Local)) {
        throw "Local file not found: $($file.Local)"
    }
    
    # Calculate relative path from $RemoteOpsDir
    $RelativePath = $file.Remote.Replace($RemoteOpsDir, "").TrimStart("/")
    $DestFile = Join-Path $StagingDir $RelativePath
    $DestDir = Split-Path $DestFile -Parent
    
    if (-not (Test-Path $DestDir)) {
        New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
    }
    
    Write-Host "Copying $($file.Local) to staging..."
    Copy-Item $file.Local $DestFile
}

Write-Host "Creating archive $ArchiveName ..."
# Use tar.exe which is available in modern Windows
& tar.exe -czf $ArchivePath -C $StagingDir .

Write-Host "Creating remote directory and uploading archive to $ServerHost ..."
& ssh $ServerHost "mkdir -p '$RemoteOpsDir'"
& scp $ArchivePath ("{0}:{1}" -f $ServerHost, "$RemoteOpsDir/$ArchiveName")

Write-Host "Extracting archive on server..."
& ssh $ServerHost "cd '$RemoteOpsDir' && tar -xzf $ArchiveName && rm $ArchiveName"

Write-Host "Marking shell scripts as executable ..."
& ssh $ServerHost "chmod +x '$RemoteOpsDir/event_refresh.sh' '$RemoteOpsDir/install_current_event_crontab.sh'"

Write-Host "Cleaning up local temporary files..."
Remove-Item -Recurse -Force $StagingDir
Remove-Item $ArchivePath

Write-Host "Upload complete."


#Requires -Version 5.1
<#
.SYNOPSIS
  Set up, start and stop Asset Studio on Windows (WP-17).

.DESCRIPTION
  setup             check prerequisites, write .env with generated secrets, choose folders,
                    offer to install ComfyUI, training and the pose models (each download is
                    listed with its size and needs a "y")
  start             start the host agent and ComfyUI, then the app (Docker Compose), and open it
  stop              stop the app, ComfyUI and the host agent
  status            show what runs
  logs [service]    follow logs: api, worker, web, mcp, db, or agent
  install-comfyui   install the pinned ComfyUI portable build and its nodes
  install-training  install kohya sd-scripts with its Python 3.11 environment

.EXAMPLE
  .\asset-studio.cmd setup
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('setup', 'start', 'stop', 'status', 'logs', 'install-comfyui', 'install-training', 'help')]
    [string]$Command = 'help',
    [Parameter(Position = 1)]
    [string]$Service = '',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'AssetStudio.psm1') -Force
$Root = Split-Path -Parent $PSScriptRoot

function Read-Folder {
    param([string]$Label, [string]$Current)
    $answer = Read-Host "$Label [$Current]"
    if ("$answer".Trim()) { return "$answer".Trim() }
    return $Current
}

function Get-EnvValue {
    param($Values, [string]$Key, [string]$Default)
    if ($Values.Contains($Key) -and $Values[$Key]) { return $Values[$Key] }
    return $Default
}

function Invoke-Compose {
    param([string[]]$Arguments)
    Push-Location $Root
    try { Invoke-Checked 'docker' (@('compose') + $Arguments) } finally { Pop-Location }
}

function Update-AgentEnv {
    <# Point the host agent at the installed components and the shared folders. #>
    param([string]$NativeDir)
    $values = Read-EnvFile (Join-Path $Root '.env')
    $components = Get-NativeComponents
    $comfy = (Get-ComfyUIPlan $NativeDir $components).Target
    $kohya = (Get-TrainingPlan $NativeDir $components).Target
    $agent = [ordered]@{
        TOKEN        = (Get-EnvValue $values 'ASSET_STUDIO_AGENT_TOKEN' '')
        PORT         = (Get-EnvValue $values 'ASSET_STUDIO_AGENT_PORT' '8410')
        COMFYUI_PORT = (Get-EnvValue $values 'ASSET_STUDIO_COMFYUI_PORT' '8188')
        MODELS_DIR   = (Resolve-HostPath $Root (Get-EnvValue $values 'ASSET_STUDIO_MODELS_HOST_DIR' './models'))
        TRAINING_DIR = (Resolve-HostPath $Root (Get-EnvValue $values 'ASSET_STUDIO_TRAINING_HOST_DIR' './training'))
        LOG_DIR      = (Get-RunDir $Root)
    }
    if (Test-Path -LiteralPath (Join-Path $comfy 'ComfyUI\main.py')) { $agent['COMFYUI_DIR'] = $comfy }
    if (Test-Path -LiteralPath (Join-Path $kohya '.venv\Scripts\python.exe')) { $agent['KOHYA_DIR'] = $kohya }
    Write-AgentEnv $Root $agent
}

function Invoke-Setup {
    Write-Host 'Asset Studio setup'
    Write-Host ''
    $checks = Get-Prerequisites $Root
    foreach ($c in $checks) {
        $mark = if ($c.Ok) { 'ok' } elseif ($c.Required) { 'MISSING' } else { 'warning' }
        Write-Host ('  [{0}] {1}: {2}' -f $mark, $c.Name, $c.Detail)
    }
    if (@($checks | Where-Object { $_.Required -and -not $_.Ok }).Count) {
        throw 'Fix the missing items above, then run setup again.'
    }

    $generated = @(Initialize-EnvFile $Root)
    if ($generated.Count) { Write-Host "Generated secrets in .env: $($generated -join ', ')" }
    else { Write-Host '.env: the secrets are already set and were kept.' }
    $envPath = Join-Path $Root '.env'
    $values = Read-EnvFile $envPath

    Write-Host ''
    Write-Host 'Press Enter to keep the value in brackets.'
    $native = Read-Folder 'Folder for ComfyUI and training (about 15 GB)' (Resolve-HostPath $Root (Get-EnvValue $values 'ASSET_STUDIO_NATIVE_DIR' './data/native'))
    $nativeDir = Resolve-HostPath $Root $native
    Set-EnvValues $envPath ([ordered]@{ ASSET_STUDIO_NATIVE_DIR = (ConvertTo-ComposePath $nativeDir) })

    $comfy = Install-ComfyUI $nativeDir
    Install-Training $nativeDir | Out-Null

    $updates = [ordered]@{}
    $prompts = Get-FolderPrompts
    foreach ($key in $prompts.Keys) {
        $current = Get-EnvValue $values $key '.'
        $default = Resolve-HostPath $Root $current
        # The app and ComfyUI must see the same model files.
        if ($key -eq 'ASSET_STUDIO_MODELS_HOST_DIR' -and $comfy -and $current -eq './models') {
            $default = Join-Path $comfy 'ComfyUI\models'
        }
        $path = Resolve-HostPath $Root (Read-Folder $prompts[$key] $default)
        New-Item -ItemType Directory -Force -Path $path | Out-Null
        $updates[$key] = ConvertTo-ComposePath $path
    }
    Set-EnvValues $envPath $updates
    Update-AgentEnv $nativeDir
    Write-Host 'Wrote .env and host-agent\.env.'

    Write-Host ''
    Write-Host 'Pose detection (DWPose) needs two model files: about 350 MB from huggingface.co, Apache-2.0.'
    Write-Host 'Without them poses are set by hand in the pose editor.'
    $answer = Read-Host 'Install the pose detection models now (builds the app images first)? Type y to continue [y/N]'
    if ("$answer".Trim() -match '^(y|yes|t|tak)$') {
        Invoke-Compose @('run', '--rm', 'worker', 'python', '-m', 'asset_studio.modules.poses.install')
    }

    Write-Host ''
    Write-Host 'Setup is done. Start Asset Studio with: .\asset-studio.cmd start'
}

function Invoke-Start {
    $settings = Get-Settings $Root
    if ($settings.Provider -eq 'comfyui') {
        Start-HostAgent $Root $settings
        try {
            Invoke-Agent $settings 'POST' '/engine:start' 60 | Out-Null
            Write-Host 'ComfyUI: starting (generation jobs wait in the queue until it is ready).'
        } catch {
            Write-Host "ComfyUI was not started: $($_.Exception.Message)" -ForegroundColor Yellow
            Write-Host 'Install it with: .\asset-studio.cmd install-comfyui' -ForegroundColor Yellow
        }
    }
    # --build: after an update the images are rebuilt (cached layers make it quick otherwise);
    # without it Compose would keep running the images of an older version.
    Invoke-Compose @('up', '-d', '--build')
    $url = "http://127.0.0.1:$($settings.WebPort)"
    Wait-Until {
        try { (Invoke-WebRequest -UseBasicParsing -Uri "$url/api/v1/system/health" -TimeoutSec 3).StatusCode -eq 200 }
        catch { $false }
    } 240 'Asset Studio'
    Write-Host "Asset Studio is running: $url"
    if (-not $NoBrowser) { Start-Process $url }
}

function Invoke-Stop {
    $settings = Get-Settings $Root
    Invoke-Compose @('stop')
    Stop-HostAgent $Root $settings
}

function Invoke-Status {
    $settings = Get-Settings $Root
    Invoke-Compose @('ps')
    if (Test-Agent $settings) {
        $engine = Invoke-Agent $settings 'GET' '/engine'
        Write-Host "Host agent: running. Engine: $($engine | ConvertTo-Json -Compress)"
    } else {
        Write-Host 'Host agent: not running.'
    }
    Write-Host "Web UI: http://127.0.0.1:$($settings.WebPort)"
}

function Invoke-Logs {
    if ($Service -eq 'agent') {
        Get-Content -LiteralPath (Join-Path (Get-RunDir $Root) 'host-agent.log') -Tail 200 -Wait
        return
    }
    $arguments = @('logs', '--follow', '--tail', '200')
    if ($Service) { $arguments += $Service }
    Invoke-Compose $arguments
}

try {
    switch ($Command) {
        'setup' { Invoke-Setup }
        'start' { Invoke-Start }
        'stop' { Invoke-Stop }
        'status' { Invoke-Status }
        'logs' { Invoke-Logs }
        'install-comfyui' {
            $dir = (Get-Settings $Root).NativeDir
            if (Install-ComfyUI $dir) { Update-AgentEnv $dir }
        }
        'install-training' {
            $dir = (Get-Settings $Root).NativeDir
            if (Install-Training $dir) { Update-AgentEnv $dir }
        }
        default {
            Write-Host @'
Asset Studio on Windows

  asset-studio setup             check prerequisites, write .env with generated secrets, choose
                                 folders, offer to install ComfyUI, training and pose models
                                 (every download is listed with its size and needs a "y")
  asset-studio start [-NoBrowser] start the host agent and ComfyUI, then the app, and open it
  asset-studio stop              stop the app, ComfyUI and the host agent
  asset-studio status            show what runs
  asset-studio logs [service]    follow logs: api, worker, web, mcp, db or agent
  asset-studio install-comfyui   install the pinned ComfyUI portable build and its nodes
  asset-studio install-training  install kohya sd-scripts with its Python 3.11 environment
'@
        }
    }
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

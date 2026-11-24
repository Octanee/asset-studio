#Requires -Version 5.1
<#
  Asset Studio setup and start (WP-17, Infrastructure "Startup workflow", NFR-013, NFR-014).

  Windows PowerShell 5.1 compatible and ASCII only, so it runs on a stock Windows machine.
  Every download is listed with its source and size and needs an explicit "y"; pinned files
  are checked against their size and SHA-256 before they are used.
#>
Set-StrictMode -Version 3.0

$script:Utf8 = New-Object System.Text.UTF8Encoding($false)
$script:Invariant = [Globalization.CultureInfo]::InvariantCulture
$script:Secrets = @(
    'ASSET_STUDIO_DB_PASSWORD',
    'ASSET_STUDIO_SESSION_SECRET',
    'ASSET_STUDIO_MCP_TOKEN',
    'ASSET_STUDIO_WORKER_TOKEN',
    'ASSET_STUDIO_AGENT_TOKEN'
)
$script:Folders = [ordered]@{
    'ASSET_STUDIO_MODELS_HOST_DIR'   = 'Model folder (shared with ComfyUI)'
    'ASSET_STUDIO_EXPORTS_HOST_DIR'  = 'Export folder (publishing targets live inside it)'
    'ASSET_STUDIO_BACKUPS_HOST_DIR'  = 'Backup folder'
    'ASSET_STUDIO_TRAINING_HOST_DIR' = 'Training exchange folder'
}

# --- small helpers ------------------------------------------------------------------------

function Get-NativeComponents {
    param([string]$Path = (Join-Path $PSScriptRoot 'native-components.json'))
    return [IO.File]::ReadAllText($Path, $script:Utf8) | ConvertFrom-Json
}

function Get-FolderPrompts {
    return $script:Folders
}

function Format-Size {
    param([double]$Bytes)
    if ($Bytes -ge 1GB) { return [string]::Format($script:Invariant, '{0:0.0} GB', $Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return [string]::Format($script:Invariant, '{0:0} MB', $Bytes / 1MB) }
    return [string]::Format($script:Invariant, '{0:0} KB', [math]::Max(1, $Bytes / 1KB))
}

function New-Secret {
    param([int]$Bytes = 32)
    $buffer = New-Object byte[] $Bytes
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return ([Convert]::ToBase64String($buffer)).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Resolve-HostPath {
    <# An absolute path for a value from .env (relative values are relative to the repo). #>
    param([string]$Root, [string]$Value)
    if ([IO.Path]::IsPathRooted($Value)) { $path = $Value } else { $path = Join-Path $Root $Value }
    return [IO.Path]::GetFullPath($path)
}

function ConvertTo-ComposePath {
    <# Docker Compose on Windows takes D:/folder; forward slashes avoid escaping in .env. #>
    param([string]$Path)
    return $Path.Replace('\', '/')
}

function Invoke-Native {
    <# Run a program, collect its output and exit code (stderr does not stop the script). #>
    param([string]$File, [string[]]$Arguments = @())
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $File @Arguments 2>&1 | ForEach-Object { "$_" }
        return [pscustomobject]@{ Code = $LASTEXITCODE; Output = @($output) }
    } finally {
        $ErrorActionPreference = $old
    }
}

function Invoke-Checked {
    <# Run a program with its output on screen (not in the function's return value); a
       non-zero exit code is an error. #>
    param([string]$File, [string[]]$Arguments = @())
    & $File @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "$File $($Arguments -join ' ') failed with exit code $LASTEXITCODE." }
}

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# --- .env files -----------------------------------------------------------------------------

function Read-EnvFile {
    param([string]$Path)
    $values = [ordered]@{}
    if (Test-Path -LiteralPath $Path) {
        foreach ($line in [IO.File]::ReadAllLines($Path, $script:Utf8)) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $values[$Matches[1]] = $Matches[2] }
        }
    }
    return $values
}

function Set-EnvValues {
    <# Change keys in place (comments and order stay) and append keys that are missing. #>
    param([string]$Path, [Collections.IDictionary]$Values)
    $lines = New-Object 'System.Collections.Generic.List[string]'
    if (Test-Path -LiteralPath $Path) {
        foreach ($line in [IO.File]::ReadAllLines($Path, $script:Utf8)) { $lines.Add($line) }
    }
    $done = @{}
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=' -and $Values.Contains($Matches[1])) {
            $key = $Matches[1]
            $lines[$i] = "$key=$($Values[$key])"
            $done[$key] = $true
        }
    }
    foreach ($key in $Values.Keys) {
        if (-not $done.ContainsKey($key)) { $lines.Add("$key=$($Values[$key])") }
    }
    [IO.File]::WriteAllText($Path, (($lines -join "`n") + "`n"), $script:Utf8)
}

function Initialize-EnvFile {
    <# .env from .env.example with every empty or placeholder secret generated. Existing
       values are never replaced (a new database password would lock out the old volume).
       Returns the keys that were generated. #>
    param([string]$Root)
    $path = Join-Path $Root '.env'
    if (-not (Test-Path -LiteralPath $path)) {
        Copy-Item -LiteralPath (Join-Path $Root '.env.example') -Destination $path
    }
    $current = Read-EnvFile $path
    $new = [ordered]@{}
    foreach ($key in $script:Secrets) {
        $value = if ($current.Contains($key)) { $current[$key] } else { '' }
        if (-not $value -or $value -eq 'change-me') { $new[$key] = New-Secret }
    }
    if ($new.Count) { Set-EnvValues $path $new }
    return @($new.Keys)
}

function Write-AgentEnv {
    <# host-agent/.env: the agent reads it from its working folder (pydantic settings). #>
    param([string]$Root, [Collections.IDictionary]$Values)
    $prefixed = [ordered]@{}
    foreach ($key in $Values.Keys) { $prefixed["ASSET_STUDIO_AGENT_$key"] = $Values[$key] }
    Set-EnvValues (Join-Path $Root 'host-agent\.env') $prefixed
}

# --- prerequisites --------------------------------------------------------------------------

function Get-Prerequisites {
    param([string]$Root, [double]$MinFreeGB = 30)
    $checks = New-Object 'System.Collections.Generic.List[object]'
    $add = {
        param($Name, $Ok, $Required, $Detail)
        $checks.Add([pscustomobject]@{ Name = $Name; Ok = [bool]$Ok; Required = $Required; Detail = $Detail })
    }
    if (Test-Command 'docker') {
        $info = Invoke-Native 'docker' @('info', '--format', '{{.ServerVersion}}')
        & $add 'Docker' ($info.Code -eq 0) $true $(if ($info.Code -eq 0) { "engine $($info.Output[0])" } else { 'installed but not running: start Docker Desktop' })
        $compose = Invoke-Native 'docker' @('compose', 'version', '--short')
        & $add 'Docker Compose' ($compose.Code -eq 0) $true $(if ($compose.Code -eq 0) { $compose.Output[0] } else { 'missing' })
    } else {
        & $add 'Docker' $false $true 'install Docker Desktop (WSL2 backend)'
    }
    $git = Test-Command 'git'
    & $add 'Git' $git $true $(if ($git) { 'found' } else { 'needed for the pinned ComfyUI nodes and kohya: winget install Git.Git' })
    $uv = Test-Command 'uv'
    & $add 'uv' $uv $true $(if ($uv) { 'found' } else { 'runs the host agent and the training environment: winget install astral-sh.uv' })
    $gpu = Test-Command 'nvidia-smi'
    $detail = 'NVIDIA driver not found: generation and training need an NVIDIA GPU'
    if ($gpu) {
        $q = Invoke-Native 'nvidia-smi' @('--query-gpu=name,memory.total', '--format=csv,noheader')
        if ($q.Code -eq 0) { $detail = $q.Output[0] } else { $gpu = $false }
    }
    & $add 'NVIDIA GPU' $gpu $false $detail
    $drive = (Split-Path -Qualifier ([IO.Path]::GetFullPath($Root))).TrimEnd(':')
    $free = (Get-PSDrive -Name $drive).Free
    & $add 'Free disk' ($free -ge $MinFreeGB * 1GB) $false "$(Format-Size $free) free on ${drive}: (about $MinFreeGB GB needed with ComfyUI, training and models)"
    return $checks
}

# --- downloads ------------------------------------------------------------------------------

function Get-FileSha256 {
    param([string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Save-VerifiedFile {
    <# Download with resume (curl.exe ships with Windows 10 and 11), then check size and
       SHA-256. A file that does not match is deleted and never used. #>
    param([string]$Url, [string]$Destination, [long]$Bytes, [string]$Sha256)
    if (Test-Path -LiteralPath $Destination) {
        if ((Get-FileSha256 $Destination) -eq $Sha256) { return $Destination }
        Remove-Item -LiteralPath $Destination
    }
    $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
    if (-not (Test-Path -LiteralPath $curl)) { $curl = 'curl.exe' }
    $part = "$Destination.part"
    if ((Test-Path -LiteralPath $part) -and (Get-Item -LiteralPath $part).Length -gt $Bytes) {
        Remove-Item -LiteralPath $part
    }
    & $curl --fail --location --retry 3 --continue-at - --progress-bar --output $part $Url
    if ($LASTEXITCODE -ne 0) {
        throw "Download failed (curl exit code $LASTEXITCODE): $Url. Run the same command again to resume."
    }
    $size = (Get-Item -LiteralPath $part).Length
    if ($size -ne $Bytes) {
        Remove-Item -LiteralPath $part
        throw "Unexpected size for $(Split-Path -Leaf $Destination): $size bytes, expected $Bytes. The file was removed."
    }
    if ((Get-FileSha256 $part) -ne $Sha256) {
        Remove-Item -LiteralPath $part
        throw "Checksum mismatch for $(Split-Path -Leaf $Destination). The file was removed and not used."
    }
    Move-Item -LiteralPath $part -Destination $Destination
    return $Destination
}

function New-PlanItem {
    param([string]$Name, [string]$Source, [double]$Bytes, [bool]$Approximate = $false, [string]$Licence = '')
    return [pscustomobject]@{ Name = $Name; Source = $Source; Bytes = $Bytes; Approximate = $Approximate; Licence = $Licence }
}

function Get-PlanTotal {
    param([object[]]$Items)
    $sum = 0.0
    foreach ($i in $Items) { $sum += $i.Bytes }
    return $sum
}

function Confirm-Plan {
    <# List what would be downloaded (name, host, size, licence) and ask for a "y". #>
    param([string]$Title, [object[]]$Items, [scriptblock]$Ask = { param($Question) Read-Host $Question })
    Write-Host ''
    Write-Host $Title
    foreach ($i in $Items) {
        $hostName = ([Uri]$i.Source).Host
        $size = Format-Size $i.Bytes
        if ($i.Approximate) { $size = "about $size" }
        $licence = if ($i.Licence) { " - $($i.Licence)" } else { '' }
        Write-Host "  - $($i.Name)  [$hostName, $size$licence]"
    }
    $total = Format-Size (Get-PlanTotal $Items)
    $answer = & $Ask "Download and install these (about $total in total)? Type y to continue [y/N]"
    return ("$answer".Trim() -match '^(y|yes|t|tak)$')
}

function Test-LongPaths {
    try {
        $key = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction Stop
        return $key.LongPathsEnabled -eq 1
    } catch {
        return $false
    }
}

function Assert-PathRoom {
    <# Without Windows long paths a full path has at most 259 characters; the portable Python
       and the training venv nest deeply, so a long install folder breaks them. #>
    param([string]$InstallDir, [int]$Deepest, [bool]$LongPaths = (Test-LongPaths))
    $max = 259 - 1 - $Deepest
    if (-not $LongPaths -and $InstallDir.Length -gt $max) {
        throw ("The folder $InstallDir has $($InstallDir.Length) characters; with Windows long paths off " +
            "it may have at most $max (files inside are nested deeply). Choose a shorter folder, " +
            'for example C:\AssetStudio, or enable long paths in Windows.')
    }
}

# --- ComfyUI (portable, pinned) -------------------------------------------------------------

function Get-ComfyUIPlan {
    param([string]$InstallDir, $Components = (Get-NativeComponents))
    $target = Join-Path $InstallDir $Components.comfyui.folder
    $items = @()
    if (-not (Test-Path -LiteralPath (Join-Path $target 'ComfyUI\main.py'))) {
        $z = $Components.sevenZip
        $c = $Components.comfyui
        $items += New-PlanItem $z.name $z.url $z.bytes $false $z.licence
        $items += New-PlanItem $c.name $c.url $c.bytes $false $c.licence
    }
    foreach ($n in $Components.comfyuiNodes) {
        if (-not (Test-Path -LiteralPath (Join-Path $target "ComfyUI\custom_nodes\$($n.name)"))) {
            $items += New-PlanItem "$($n.name) at $($n.commit.Substring(0, 7))" $n.repo $n.approxBytes $true $n.licence
        }
    }
    return [pscustomobject]@{ Target = $target; Items = $items }
}

function Install-ComfyUI {
    param(
        [string]$InstallDir,
        [scriptblock]$Ask = { param($Question) Read-Host $Question },
        $Components = (Get-NativeComponents)
    )
    $components = $Components
    $plan = Get-ComfyUIPlan $InstallDir $components
    if (-not $plan.Items.Count) {
        Write-Host "ComfyUI is already installed in $($plan.Target)."
        return $plan.Target
    }
    Assert-PathRoom $InstallDir $components.comfyui.deepestPath
    if (-not (Confirm-Plan 'ComfyUI (generation engine) needs:' $plan.Items $Ask)) {
        Write-Host 'Skipped. Install it later with: asset-studio install-comfyui'
        return $null
    }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $plan.Target 'ComfyUI\main.py'))) {
        $downloads = Join-Path $InstallDir 'downloads'
        New-Item -ItemType Directory -Force -Path $downloads | Out-Null
        $z = $components.sevenZip
        $c = $components.comfyui
        $seven = Save-VerifiedFile $z.url (Join-Path $downloads $z.file) $z.bytes $z.sha256
        $archive = Save-VerifiedFile $c.url (Join-Path $downloads $c.file) $c.bytes $c.sha256
        Write-Host 'Extracting ComfyUI (a few minutes)...'
        Invoke-Checked $seven @('x', $archive, "-o$InstallDir", '-y', '-bso0', '-bsp1')
    }
    foreach ($n in $components.comfyuiNodes) {
        $dir = Join-Path $plan.Target "ComfyUI\custom_nodes\$($n.name)"
        if (-not (Test-Path -LiteralPath $dir)) {
            Invoke-Checked 'git' @('clone', '--quiet', $n.repo, $dir)
            Invoke-Checked 'git' @('-C', $dir, 'checkout', '--quiet', $n.commit)
        }
    }
    Write-Host "ComfyUI is installed in $($plan.Target)."
    return $plan.Target
}

# --- training (kohya sd-scripts, pinned) ----------------------------------------------------

function Get-TrainingPlan {
    param([string]$InstallDir, $Components = (Get-NativeComponents))
    $k = $Components.kohya
    $target = Join-Path $InstallDir $k.folder
    $items = @()
    if (-not (Test-Path -LiteralPath (Join-Path $target '.venv\Scripts\python.exe'))) {
        $items += New-PlanItem "$($k.name) at $($k.commit.Substring(0, 7))" $k.repo $k.approxBytes.source $true $k.licence
        $items += New-PlanItem "Python $($k.python) (through uv, if not present)" 'https://github.com/astral-sh/python-build-standalone' $k.approxBytes.python $true 'PSF'
        $items += New-PlanItem "PyTorch with CUDA ($($k.torch -join ', '))" $k.torchIndex $k.approxBytes.torch $true 'BSD-3-Clause'
        $items += New-PlanItem 'sd-scripts requirements (accelerate, transformers, diffusers, bitsandbytes, ...)' 'https://pypi.org' $k.approxBytes.requirements $true 'various open-source'
    }
    return [pscustomobject]@{ Target = $target; Items = $items }
}

function Install-Training {
    param(
        [string]$InstallDir,
        [scriptblock]$Ask = { param($Question) Read-Host $Question },
        $Components = (Get-NativeComponents)
    )
    $components = $Components
    $k = $components.kohya
    $plan = Get-TrainingPlan $InstallDir $components
    if (-not $plan.Items.Count) {
        Write-Host "Training (kohya) is already installed in $($plan.Target)."
        return $plan.Target
    }
    Assert-PathRoom $InstallDir $k.deepestPath
    if (-not (Confirm-Plan 'LoRA training (kohya sd-scripts in its own Python 3.11 environment) needs:' $plan.Items $Ask)) {
        Write-Host 'Skipped. Install it later with: asset-studio install-training'
        return $null
    }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $plan.Target '.git'))) {
        Invoke-Checked 'git' @('clone', '--quiet', $k.repo, $plan.Target)
    }
    Invoke-Checked 'git' @('-C', $plan.Target, 'checkout', '--quiet', $k.commit)
    $python = Join-Path $plan.Target '.venv\Scripts\python.exe'
    $oldUtf8 = $env:PYTHONUTF8
    $env:PYTHONUTF8 = '1'  # NFR-014: UTF-8 I/O for every Python subprocess
    Push-Location $plan.Target
    try {
        Invoke-Checked 'uv' @('venv', '--python', $k.python, '.venv')
        Invoke-Checked 'uv' (@('pip', 'install', '--python', $python, '--index-url', $k.torchIndex) + @($k.torch))
        Invoke-Checked 'uv' @('pip', 'install', '--python', $python, '-r', 'requirements.txt')
    } finally {
        Pop-Location
        $env:PYTHONUTF8 = $oldUtf8
    }
    Write-Host "Training is installed in $($plan.Target)."
    return $plan.Target
}

# --- running --------------------------------------------------------------------------------

function Get-RunDir {
    param([string]$Root)
    $dir = Join-Path $Root 'data\run'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-Settings {
    param([string]$Root)
    $path = Join-Path $Root '.env'
    if (-not (Test-Path -LiteralPath $path)) { throw 'No .env yet. Run: asset-studio setup' }
    $values = Read-EnvFile $path
    $get = { param($Key, $Default) if ($values.Contains($Key) -and $values[$Key]) { $values[$Key] } else { $Default } }
    return [pscustomobject]@{
        WebPort    = [int](& $get 'ASSET_STUDIO_WEB_PORT' '8480')
        AgentPort  = [int](& $get 'ASSET_STUDIO_AGENT_PORT' '8410')
        AgentToken = (& $get 'ASSET_STUDIO_AGENT_TOKEN' '')
        Provider   = (& $get 'ASSET_STUDIO_ENGINE_PROVIDER' 'comfyui')
        NativeDir  = (Resolve-HostPath $Root (& $get 'ASSET_STUDIO_NATIVE_DIR' './data/native'))
    }
}

function Invoke-Agent {
    param($Settings, [string]$Method = 'GET', [string]$Path = '/health', [int]$TimeoutSec = 3)
    $uri = "http://127.0.0.1:$($Settings.AgentPort)$Path"
    $headers = @{ Authorization = "Bearer $($Settings.AgentToken)" }
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -TimeoutSec $TimeoutSec
}

function Test-Agent {
    param($Settings)
    try { Invoke-Agent $Settings | Out-Null; return $true } catch { return $false }
}

function Wait-Until {
    param([scriptblock]$Condition, [int]$Seconds, [string]$What)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return }
        Start-Sleep -Seconds 2
    }
    throw "$What did not become ready within $Seconds seconds."
}

function Start-HostAgent {
    param([string]$Root, $Settings)
    if (Test-Agent $Settings) { Write-Host 'Host agent: already running.'; return }
    $run = Get-RunDir $Root
    $env:PYTHONUTF8 = '1'
    # cmd.exe writes the logs, so Start-Process can use the shell and the agent does not
    # inherit this console's handles (a caller piping our output would never see its end).
    $out = Join-Path $run 'host-agent.out.log'
    $err = Join-Path $run 'host-agent.log'
    $line = "uv run python -m asset_studio_host_agent.app 1>>`"$out`" 2>>`"$err`""
    $process = Start-Process -FilePath $env:ComSpec -ArgumentList @('/d', '/c', $line) `
        -WorkingDirectory (Join-Path $Root 'host-agent') -WindowStyle Hidden -PassThru
    [IO.File]::WriteAllText((Join-Path $run 'host-agent.pid'), "$($process.Id)", $script:Utf8)
    Write-Host 'Host agent: starting (the first start prepares its environment)...'
    Wait-Until { Test-Agent $Settings } 180 'The host agent'
    Write-Host 'Host agent: running.'
}

function Stop-HostAgent {
    param([string]$Root, $Settings)
    $pidFile = Join-Path (Get-RunDir $Root) 'host-agent.pid'
    if (Test-Agent $Settings) {
        try { Invoke-Agent $Settings 'POST' '/engine:stop' 30 | Out-Null } catch { Write-Host "Engine stop: $($_.Exception.Message)" }
    }
    if (Test-Path -LiteralPath $pidFile) {
        $id = [IO.File]::ReadAllText($pidFile).Trim()
        Invoke-Native 'taskkill' @('/PID', $id, '/T', '/F') | Out-Null  # uv and its Python child
        Remove-Item -LiteralPath $pidFile
        Write-Host 'Host agent: stopped.'
    }
}

Export-ModuleMember -Function *

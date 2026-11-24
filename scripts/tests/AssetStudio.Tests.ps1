#Requires -Version 5.1
<#
  Tests for the setup module (WP-17). Plain asserts so they run on a stock Windows
  PowerShell 5.1 without installing a test framework; no network and no real installs
  (downloads use file:// URLs through curl.exe).
  Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\AssetStudio.Tests.ps1
#>
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3.0
Import-Module (Join-Path $PSScriptRoot '..\AssetStudio.psm1') -Force

$script:Failures = New-Object 'System.Collections.Generic.List[string]'
$script:Count = 0
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Test {
    param([string]$Name, [scriptblock]$Body)
    $script:Count++
    try { & $Body; Write-Host "  ok    $Name" }
    catch { $script:Failures.Add("$Name : $($_.Exception.Message)"); Write-Host "  FAIL  $Name : $($_.Exception.Message)" -ForegroundColor Red }
}

function Assert-Equal {
    param($Expected, $Actual, [string]$What = 'value')
    if ($Expected -ne $Actual) { throw "$What : expected '$Expected', got '$Actual'" }
}

function Assert-True {
    param($Condition, [string]$What)
    if (-not $Condition) { throw "expected: $What" }
}

function Assert-Throws {
    param([scriptblock]$Body, [string]$Like)
    try { & $Body } catch {
        if ($_.Exception.Message -notlike "*$Like*") { throw "wrong error: $($_.Exception.Message)" }
        return
    }
    throw "expected an error like '$Like'"
}

function New-TempDir {
    # Short, so install plans pass the long-path check on machines with long paths off.
    $dir = Join-Path ([IO.Path]::GetTempPath()) ('as-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Path $dir | Out-Null
    return $dir
}

function ConvertTo-FileUrl {
    param([string]$Path)
    return ([Uri](Resolve-Path -LiteralPath $Path).Path).AbsoluteUri
}

Write-Host 'AssetStudio module'

Test 'sizes are written with invariant decimals' {
    Assert-Equal '1.9 GB' (Format-Size 2085169944) 'GB'
    Assert-Equal '586 KB' (Format-Size 600000) 'KB'
    Assert-Equal '350 MB' (Format-Size (350MB)) 'MB'
}

Test 'secrets are long, URL-safe and different each time' {
    $a = New-Secret
    $b = New-Secret
    Assert-True ($a -match '^[A-Za-z0-9_-]{43}$') "a 43-character base64url secret, got $a"
    Assert-True ($a -ne $b) 'two different secrets'
}

Test 'relative .env paths resolve against the repository' {
    $root = New-TempDir
    Assert-Equal ([IO.Path]::GetFullPath((Join-Path $root 'models'))) (Resolve-HostPath $root './models') 'relative'
    Assert-Equal 'C:\data\x' (Resolve-HostPath $root 'C:\data\x') 'absolute'
    Assert-Equal 'C:/data/x' (ConvertTo-ComposePath 'C:\data\x') 'compose form'
}

Test '.env values change in place, comments stay and new keys are appended' {
    $root = New-TempDir
    $path = Join-Path $root '.env'
    [IO.File]::WriteAllText($path, "# comment`nA=1`n`nB=two`n", $Utf8)
    Set-EnvValues $path ([ordered]@{ B = '2'; C = 'three' })
    Assert-Equal "# comment`nA=1`n`nB=2`nC=three`n" ([IO.File]::ReadAllText($path)) 'file'
    $values = Read-EnvFile $path
    Assert-Equal '1' $values['A'] 'A'
    Assert-Equal 'three' $values['C'] 'C'
}

Test 'setup generates missing secrets once and never replaces a set one' {
    $root = New-TempDir
    [IO.File]::WriteAllText((Join-Path $root '.env.example'), "ASSET_STUDIO_DB_PASSWORD=change-me`nASSET_STUDIO_SESSION_SECRET=change-me`nASSET_STUDIO_MCP_TOKEN=`nASSET_STUDIO_WORKER_TOKEN=`nASSET_STUDIO_AGENT_TOKEN=`nASSET_STUDIO_WEB_PORT=8480`n", $Utf8)
    $first = @(Initialize-EnvFile $root)
    Assert-Equal 5 $first.Count 'generated on the first run'
    $values = Read-EnvFile (Join-Path $root '.env')
    Assert-True ($values['ASSET_STUDIO_DB_PASSWORD'] -ne 'change-me') 'the placeholder password is replaced'
    Assert-Equal '8480' $values['ASSET_STUDIO_WEB_PORT'] 'other values are kept'
    $second = @(Initialize-EnvFile $root)
    Assert-Equal 0 $second.Count 'nothing generated on the second run'
    Assert-Equal $values['ASSET_STUDIO_AGENT_TOKEN'] (Read-EnvFile (Join-Path $root '.env'))['ASSET_STUDIO_AGENT_TOKEN'] 'the token is kept'
}

Test 'the host agent .env gets prefixed keys' {
    $root = New-TempDir
    New-Item -ItemType Directory -Path (Join-Path $root 'host-agent') | Out-Null
    Write-AgentEnv $root ([ordered]@{ TOKEN = 't'; COMFYUI_DIR = 'D:\x' })
    $values = Read-EnvFile (Join-Path $root 'host-agent\.env')
    Assert-Equal 't' $values['ASSET_STUDIO_AGENT_TOKEN'] 'token'
    Assert-Equal 'D:\x' $values['ASSET_STUDIO_AGENT_COMFYUI_DIR'] 'ComfyUI dir'
}

Test 'every pinned component has an https source, a size and a hash or commit' {
    $c = Get-NativeComponents
    foreach ($item in @($c.sevenZip, $c.comfyui)) {
        Assert-True ($item.url -like 'https://*') "https url for $($item.name)"
        Assert-True ($item.bytes -gt 0) "size for $($item.name)"
        Assert-True ($item.sha256 -match '^[0-9a-f]{64}$') "sha256 for $($item.name)"
    }
    foreach ($item in @($c.comfyuiNodes) + @($c.kohya)) {
        Assert-True ($item.repo -like 'https://github.com/*') "https repo for $($item.name)"
        Assert-True ($item.commit -match '^[0-9a-f]{40}$') "full commit for $($item.name)"
    }
    Assert-True ($c.kohya.torchIndex -like 'https://download.pytorch.org/*') 'the official PyTorch index'
}

Test 'install plans list every missing download and nothing once installed' {
    $dir = New-TempDir
    $comfy = Get-ComfyUIPlan $dir
    Assert-Equal 3 $comfy.Items.Count 'ComfyUI plan items'
    Assert-True ((Get-PlanTotal $comfy.Items) -gt 1.9GB) 'the ComfyUI plan is about 2 GB'
    $training = Get-TrainingPlan $dir
    Assert-Equal 4 $training.Items.Count 'training plan items'
    New-Item -ItemType Directory -Force -Path (Join-Path $comfy.Target 'ComfyUI\custom_nodes\ComfyUI_IPAdapter_plus') | Out-Null
    [IO.File]::WriteAllText((Join-Path $comfy.Target 'ComfyUI\main.py'), '', $Utf8)
    New-Item -ItemType Directory -Force -Path (Join-Path $training.Target '.venv\Scripts') | Out-Null
    [IO.File]::WriteAllText((Join-Path $training.Target '.venv\Scripts\python.exe'), '', $Utf8)
    Assert-Equal 0 @((Get-ComfyUIPlan $dir).Items).Count 'nothing left for ComfyUI'
    Assert-Equal 0 @((Get-TrainingPlan $dir).Items).Count 'nothing left for training'
}

Test 'nothing is installed without a "y"' {
    $items = @(New-PlanItem 'Thing' 'https://example.invalid/x' 1MB)
    foreach ($no in @('', 'n', 'no', 'maybe')) {
        Assert-True (-not (Confirm-Plan 'Plan' $items { param($q) $no })) "'$no' is not a yes"
    }
    foreach ($yes in @('y', 'Y', 'yes', 'tak', ' t ')) {
        Assert-True (Confirm-Plan 'Plan' $items { param($q) $yes }) "'$yes' is a yes"
    }
    $dir = New-TempDir
    $declined = Install-ComfyUI $dir { param($q) 'n' }
    Assert-Equal $null $declined 'a declined install returns nothing'
    Assert-Equal 0 @(Get-ChildItem -LiteralPath $dir).Count 'and writes nothing'
}

Test 'a deep install folder is refused while Windows long paths are off' {
    $deepest = (Get-NativeComponents).comfyui.deepestPath
    Assert-PathRoom 'C:\AssetStudio' $deepest $false
    $long = 'C:\' + ('x' * 90)
    Assert-Throws { Assert-PathRoom $long $deepest $false } 'Choose a shorter folder'
    Assert-PathRoom $long $deepest $true
}

Test 'a download is used only when its size and SHA-256 match' {
    $dir = New-TempDir
    $source = Join-Path $dir 'source.bin'
    [IO.File]::WriteAllBytes($source, [byte[]](1..200))
    $sha = Get-FileSha256 $source
    $url = ConvertTo-FileUrl $source
    $target = Join-Path $dir 'target.bin'
    Assert-Equal $target (Save-VerifiedFile $url $target 200 $sha) 'downloaded'
    Assert-Equal $sha (Get-FileSha256 $target) 'same content'
    Assert-Equal $target (Save-VerifiedFile 'file:///missing/never-fetched' $target 200 $sha) 'a matching file is not fetched again'

    $bad = Join-Path $dir 'bad.bin'
    Assert-Throws { Save-VerifiedFile $url $bad 200 ('0' * 64) } 'Checksum mismatch'
    Assert-True (-not (Test-Path -LiteralPath $bad)) 'no file after a checksum mismatch'
    Assert-True (-not (Test-Path -LiteralPath "$bad.part")) 'no partial file either'
    Assert-Throws { Save-VerifiedFile $url (Join-Path $dir 'size.bin') 999 $sha } 'Unexpected size'
}

Write-Host ''
if ($script:Failures.Count) {
    Write-Host "$($script:Failures.Count) of $script:Count tests failed." -ForegroundColor Red
    exit 1
}
Write-Host "All $script:Count tests passed."

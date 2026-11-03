param(
    [string]$DestinationRoot,
    [switch]$Update
)
$ErrorActionPreference = 'Stop'
$source = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\skills\ledom-growth'))
if (-not $DestinationRoot) {
    $codexBase = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex' }
    $DestinationRoot = Join-Path $codexBase 'skills'
}
$root = [IO.Path]::GetFullPath($DestinationRoot)
$target = [IO.Path]::GetFullPath((Join-Path $root 'ledom-growth'))
if ((Split-Path -Parent $target) -ne $root.TrimEnd('\')) { throw 'Target must be exactly one skill directory below destination root' }
if (-not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md'))) { throw 'Source skill missing' }
if ($source -eq $target) { throw 'Source and destination must differ' }
function Get-Inventory([string]$Base) {
    $map = @{}
    foreach ($entry in Get-ChildItem -LiteralPath $Base -Force -Recurse) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Symlink/reparse entries are not supported' }
        if (-not $entry.PSIsContainer) {
            $map[$entry.FullName.Substring($Base.Length).TrimStart('\')] = (Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash
        }
    }
    return $map
}
$expected = Get-Inventory $source
if (Test-Path -LiteralPath $target) {
    if ((Get-Item -LiteralPath $target -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Destination is a reparse point' }
    $actual = Get-Inventory $target
    $same = $expected.Count -eq $actual.Count
    foreach ($key in $expected.Keys) { if ($expected[$key] -ne $actual[$key]) { $same = $false } }
    if ($same) { Write-Output ('Already installed and hash-verified: ' + $target); exit 0 }
    if (-not $Update) { throw 'A different version exists. Use -Update explicitly to preserve it as a backup before replacement.' }
    $backupRoot = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $root) 'skill-backups'))
    $backup = [IO.Path]::GetFullPath((Join-Path $backupRoot ('ledom-growth-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '-' + [Guid]::NewGuid().ToString('N'))))
    if ((Split-Path -Parent $backup) -ne $backupRoot) { throw 'Unexpected backup target' }
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    Move-Item -LiteralPath $target -Destination $backup
    Write-Output ('Previous installation preserved: ' + $backup)
}
New-Item -ItemType Directory -Path $root -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $target -Recurse
$installed = Get-Inventory $target
if ($installed.Count -ne $expected.Count) { throw 'Installation file count mismatch' }
foreach ($key in $expected.Keys) { if ($installed[$key] -ne $expected[$key]) { throw ('Installation hash mismatch: ' + $key) } }
Write-Output ('Installed and hash-verified: ' + $target)
Write-Output ('Files: ' + $installed.Count)

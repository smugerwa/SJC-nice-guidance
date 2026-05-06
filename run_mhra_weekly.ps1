param(
    [string]$WeekEnding,
    [int]$Days = 7,
    [switch]$NoGoogle,
    [switch]$NoLlm
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}

$pythonPath = @()
if (Test-Path ".deps") { $pythonPath += (Resolve-Path ".deps").Path }
if ($env:PYTHONPATH) { $pythonPath += $env:PYTHONPATH }
if ($pythonPath.Count -gt 0) { $env:PYTHONPATH = ($pythonPath -join [IO.Path]::PathSeparator) }

$argsList = @("-m", "nice_guidance_monitor.mhra_cli", "--config", "config.json")
if ($WeekEnding) { $argsList += @("--week-ending", $WeekEnding) }
if ($Days -ne 7) { $argsList += @("--days", $Days) }
if ($NoGoogle) { $argsList += "--no-google" }
if ($NoLlm) { $argsList += "--no-llm" }

python @argsList

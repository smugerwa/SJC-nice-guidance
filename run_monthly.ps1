param(
  [string]$Month = "",
  [string]$Config = "config.json",
  [switch]$CurrentMonth,
  [switch]$NoGoogle,
  [switch]$NoLlm
)

$ErrorActionPreference = "Stop"

$python = "python"
$runtimePython = "C:\Users\soul.mugerwa\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $runtimePython) {
  $python = $runtimePython
}

$localDeps = Join-Path (Get-Location) ".deps"
if (Test-Path $localDeps) {
  if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$localDeps;$env:PYTHONPATH"
  } else {
    $env:PYTHONPATH = $localDeps
  }
}

if ($CurrentMonth -and -not $Month) {
  $Month = Get-Date -Format "MMMM yyyy"
}

$argsList = @("-m", "nice_guidance_monitor.cli", "--config", $Config)
if ($Month) {
  $argsList += @("--month", $Month)
}
if ($NoGoogle) {
  $argsList += "--no-google"
}
if ($NoLlm) {
  $argsList += "--no-llm"
}

& $python @argsList

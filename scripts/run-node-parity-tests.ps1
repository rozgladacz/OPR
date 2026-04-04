param(
    [string]$PythonExe = "python",
    [string]$NodeExe = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$SetupScript = Join-Path $PSScriptRoot "setup-tests.ps1"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

function Test-VenvPythonHealthy {
    param([string]$PythonPath)

    if (-not (Test-Path $PythonPath)) {
        return $false
    }

    & $PythonPath --version *> $null
    return ($LASTEXITCODE -eq 0)
}

if (-not (Test-VenvPythonHealthy -PythonPath $VenvPython)) {
    Write-Host "Local .venv is missing or broken. Rebuilding environment..."
    & $SetupScript -PythonExe $PythonExe -NodeExe $NodeExe -SmokeTest "tests/test_security_passwords.py"
}

if (-not (Test-VenvPythonHealthy -PythonPath $VenvPython)) {
    throw "Virtual environment is still not runnable after bootstrap: $VenvPython"
}

$nodeFromArg = $null
if ($NodeExe) {
    $expanded = [Environment]::ExpandEnvironmentVariables($NodeExe)
    if (Test-Path $expanded) {
        $nodeFromArg = [System.IO.Path]::GetFullPath($expanded)
    }
}

if ($nodeFromArg) {
    $env:NODE_BINARY = $nodeFromArg
}
elseif (-not $env:NODE_BINARY) {
    $globalNode = (Get-Command node -ErrorAction SilentlyContinue)
    if ($globalNode) {
        $env:NODE_BINARY = $globalNode.Source
    }
    else {
        $localNode = Get-ChildItem -Path (Join-Path $ProjectRoot ".tools\node") -Filter node.exe -Recurse -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($localNode) {
            $env:NODE_BINARY = $localNode.FullName
        }
    }
}

if (-not $env:NODE_BINARY) {
    Write-Host "Node binary not detected. Running bootstrap to provision Node.js..."
    & $SetupScript -PythonExe $PythonExe -NodeExe $NodeExe -SmokeTest "tests/test_security_passwords.py"
}

if (-not $env:NODE_BINARY) {
    throw "Unable to resolve NODE_BINARY."
}

$env:ENABLE_LEGACY_MATH_PARITY_TESTS = "1"

Write-Host "Using Python: $VenvPython"
& $VenvPython --version
Write-Host "Using Node: $env:NODE_BINARY"
& $env:NODE_BINARY --version

& $VenvPython -m pytest -q `
    tests/test_frontend_weapon_cost_regression.py::test_frontend_weapon_cost_matches_backend_weapon_cost_with_tolerance `
    tests/test_weapon_cost_parity.py::test_weapon_cost_internal_frontend_matches_backend `
    tests/test_weapon_cost_sandbox_parity.py::test_weapon_cost_python_node_sandbox_parity

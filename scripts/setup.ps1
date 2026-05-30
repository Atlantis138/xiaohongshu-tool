[CmdletBinding()]
param(
    [switch] $SkipBrowserInstall,
    [switch] $Force
)

$ErrorActionPreference = "Stop"

$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir = Join-Path $ProjectDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$Requirements = Join-Path $ProjectDir "requirements.txt"

function Test-PythonVersion {
    param([string] $PythonCommand)

    $script = "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    & $PythonCommand -c $script *> $null
    return $LASTEXITCODE -eq 0
}

function Get-HostPython {
    $candidates = @()

    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates += @{ Command = "py"; Args = @("-3.11") }
        $candidates += @{ Command = "py"; Args = @("-3") }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $candidates += @{ Command = "python"; Args = @() }
    }

    foreach ($candidate in $candidates) {
        $command = $candidate.Command
        $args = $candidate.Args
        $versionCheck = "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        & $command @args -c $versionCheck *> $null
        if ($LASTEXITCODE -eq 0) {
            return $candidate
        }
    }

    throw "Python 3.11 or newer was not found. Install Python from https://www.python.org/downloads/windows/ and rerun this script."
}

Push-Location $ProjectDir
try {
    if ((Test-Path -LiteralPath $VenvDir) -and $Force) {
        Remove-Item -LiteralPath $VenvDir -Recurse -Force
    }

    if (-not (Test-Path -LiteralPath $VenvPython)) {
        $hostPython = Get-HostPython
        Write-Host "Creating virtual environment at .venv"
        & $hostPython.Command @($hostPython.Args + @("-m", "venv", ".venv"))
    }

    if (-not (Test-Path -LiteralPath $VenvPython)) {
        throw "Failed to create .venv."
    }

    Write-Host "Upgrading pip"
    & $VenvPython -m pip install --upgrade pip

    Write-Host "Installing Python dependencies"
    & $VenvPython -m pip install -r $Requirements

    if (-not $SkipBrowserInstall) {
        Write-Host "Installing Playwright Chromium to the default user cache"
        & $VenvPython -m playwright install chromium
    }

    Write-Host ""
    Write-Host "Setup complete."
    Write-Host "Run the GUI with: scripts\run_gui.bat"
    Write-Host "Run the CLI with: scripts\run_scraper.bat --help"
}
finally {
    Pop-Location
}

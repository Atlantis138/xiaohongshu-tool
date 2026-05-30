param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $RemainingArgs
)

$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$Script = Join-Path $ProjectDir "xhs_scraper.py"

if (Test-Path -LiteralPath $Python) {
    & $Python $Script @RemainingArgs
} else {
    Write-Error "Project virtual environment not found. Run scripts\setup.ps1 from the project root first."
    exit 1
}
exit $LASTEXITCODE

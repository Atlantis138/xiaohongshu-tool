param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $RemainingArgs
)

$Python = "C:\Python\Python311\python.exe"
$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$Script = Join-Path $ProjectDir "xhs_scraper.py"

if (Test-Path -LiteralPath $Python) {
    & $Python $Script @RemainingArgs
} else {
    & python $Script @RemainingArgs
}
exit $LASTEXITCODE

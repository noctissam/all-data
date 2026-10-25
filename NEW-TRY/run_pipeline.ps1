# NEW-TRY: run the whole pipeline on one PDF.
#
#   .\run_pipeline.ps1 "path\to\paper.pdf"
#   .\run_pipeline.ps1 "path\to\paper.pdf" -RestartOcr
#
# Output lands in NEW-TRY\out (tables_extracted.xlsx, images, logs).

param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Pdf,
    [switch]$RestartOcr,
    [switch]$RestartAll
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $here "src"
$py = "python"

if (-not (Test-Path $Pdf)) {
    $Pdf = Join-Path (Split-Path -Parent $here) $Pdf
}
if (-not (Test-Path $Pdf)) {
    throw "PDF not found: $Pdf"
}

Set-Location $here
New-Item -ItemType Directory -Force -Path "out" | Out-Null

function Step($name, $argList) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host "  $name" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    & $py @argList
    if ($LASTEXITCODE -ne 0) { throw "$name failed (exit $LASTEXITCODE)" }
}

if ($RestartAll) {
    Remove-Item "out\img\*.png", "out\ocr\*.json", "out\grid\*", "out\page_preview\*.png" -ErrorAction SilentlyContinue
    Remove-Item "out\tables_extracted.xlsx" -ErrorAction SilentlyContinue
}

Step "1/5  detect three-line tables + render A/B images" @("$src\s1_detect_tables.py", $Pdf)

$ocrArgs = @("$src\s2_umi_ocr.py")
if ($RestartOcr) { $ocrArgs += "--restart" }
Step "2/5  Umi-OCR: A/B English (extract + verify), C Chinese (symbol donor)" $ocrArgs

Step "3/5  rebuild grid + verify A against B + symbol repair" @("$src\s3_verify_grid.py")
Step "4/5  targeted 600 dpi rescue of suspicious cells" @("$src\s4_rescue_cells.py")
Step "5/5  write excel" @("$src\s5_to_excel.py")

$book = Join-Path $here "out\tables_extracted.xlsx"
Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "  done -> $book" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Green
Start-Process explorer.exe -ArgumentList "`"$book`""

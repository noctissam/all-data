# NEW-TRY\run_reorganize.ps1 - the whole re整理 chain, one command.
#
#   .\run_reorganize.ps1              # rebuild -> names -> CAS -> copy -> verify
#   .\run_reorganize.ps1 -NoCopy      # leave the root workbook alone
#   .\run_reorganize.ps1 -SkipVerify  # skip the checks (they hit the network)
#
# Output lands in NEW-TRY\out\re整理 and a transcript in out\re整理\run.log.
#
# Two things this script exists to avoid, both of which cost real time here:
#
#   1. `python ... 2>&1 | Select-Object -First N` truncates the pipe, python dies on the
#      broken stream, and PowerShell reports a non-zero exit for a run that actually
#      succeeded. Every step here redirects to a file and reads it afterwards, so the exit
#      code means what it says.
#
#   2. The console code page mangles Chinese into mojibake. PYTHONIOENCODING is set and
#      output goes through files that are read back as UTF-8.

param(
    [switch]$NoCopy,
    [switch]$SkipVerify,
    [switch]$SkipExtract,
    [int]$Roundtrip = 40
)

$ErrorActionPreference = "Stop"
# The console code page on a zh-CN Windows install is GBK, so python's UTF-8 output is
# decoded as GBK on the way through the pipe and every Chinese character in the transcript
# becomes mojibake. Out-File -Encoding UTF8 does not help - by then it is already wrong.
# The pipe has to be told what encoding it is carrying.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$out = Join-Path $here "out\re整理"
$src = Join-Path $here "src"
$root = Split-Path -Parent $here
$log = Join-Path $out "run.log"
$env:PYTHONIOENCODING = "utf-8"

New-Item -ItemType Directory -Force -Path $out | Out-Null
"" | Set-Content -Path $log -Encoding UTF8

function Step($name, $argList) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host "  $name" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    "STEP: $name  $(Get-Date -Format 'HH:mm:ss')" | Add-Content -Path $log -Encoding UTF8

    $tmp = Join-Path $out ("_step_" + ($name -replace '[^a-zA-Z0-9]', '_') + ".txt")
    # Out-File -Encoding UTF8, not `*> $tmp`: in Windows PowerShell 5.1 the redirection
    # operator writes UTF-16LE, and reading that back as UTF-8 turns every Chinese line in
    # the transcript into mojibake.
    & python @argList 2>&1 | Out-File -FilePath $tmp -Encoding UTF8
    $code = $LASTEXITCODE

    Get-Content -Path $tmp -Encoding UTF8 | Add-Content -Path $log -Encoding UTF8
    if ($code -ne 0) {
        Get-Content -Path $tmp -Encoding UTF8 | Select-Object -Last 25 | ForEach-Object {
            Write-Host "    $_" -ForegroundColor Red
        }
        throw "$name failed (exit $code) - see $tmp and $log"
    }
    Get-Content -Path $tmp -Encoding UTF8 | Select-Object -Last 8 | ForEach-Object {
        Write-Host "    $_"
    }
}

# Resolve the scripts by glob rather than by literal name.
#
# build_rec整理.py has a Chinese filename. Windows PowerShell 5.1 decodes a BOM-less .ps1
# as ANSI, so the literal came out as "build_rec鏁寸?py" and the step died with
# "No such file or directory". Globbing keeps this script free of any non-ASCII path, which
# is immune to that decoding rule and to a future rename. This file is also saved with a
# UTF-8 BOM for the same reason.
function Py($pattern) {
    $hit = Get-ChildItem -Path $src -Filter $pattern -File -ErrorAction SilentlyContinue
    if (-not $hit) { throw "script not found in ${src}: $pattern" }
    if ($hit.Count -gt 1) { throw "pattern matched $($hit.Count) files in ${src}: $pattern" }
    $hit.FullName
}

# extract_band rebuilds the band files from each PDF's text layer. It has to run BEFORE
# repair_bands, and it is safe to re-run: the wrapped-name rejoin it performs is reported
# to out\re整理\wrap_report.txt rather than applied silently.
if (-not $SkipExtract) {
    Step "0/9  extract band tables (text layer)" @((Py "extract_band.py"))
}
# repair_bitmap rebuilds the image-only papers' tables from their OCR boxes. Those PDFs have
# no text layer at all, so the grid had to guess the column count from the rules and both got
# it wrong: two measurements written into one cell ("19.62±1.73a 18.06±2.69a") and a header
# that lives on the previous page. Every rebuild is checked to lose no row and to gain no
# cell that no merged cell in the original accounts for; the ones that fail are left alone and
# listed in out\re整理\bitmap_rebuild.txt.
Step "1/9  rebuild bitmap tables from OCR boxes" @((Py "repair_bitmap.py"), "--apply")
Step "2/9  repair merged / wrapped rows"  @((Py "repair_bands.py"))
# recover_headers runs AFTER extract_band, because extract_band rewrites the band files
# from scratch and would discard anything written into them. It fills in column headers the
# grid left blank, reading the paper's own header off the page text, and reports every
# attempt to out\re整理\header_recovery.txt - a column it cannot name is left as 列N rather
# than given a plausible guess.
Step "3/9  recover lost column headers"   @((Py "recover_headers.py"), "--apply")
Step "4/9  rebuild workbook"             @((Py "build_rec*.py"))
Step "5/9  collect compound names"       @((Py "collect_names.py"))
Step "6/9  settle two-source disagreements" @((Py "cas_crosscheck.py"), "--resolve")
Step "7/9  resolve and write CAS"        @((Py "write_cas.py"), "--cross", (Join-Path $out "cas_cross.json"))

if (-not $NoCopy) {
    $book = Join-Path $out "re整理.xlsx"
    $dest = Join-Path $root "re整理.xlsx"
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    if (Test-Path $dest) {
        Copy-Item $dest (Join-Path $out "_backup_root_$ts.xlsx") -Force
    }
    Copy-Item $book $dest -Force
    Write-Host ""
    Write-Host ("  copied -> {0}" -f $dest) -ForegroundColor Green
    "copied -> $dest" | Add-Content -Path $log -Encoding UTF8
}

if (-not $SkipVerify) {
    Step "8/9  verify (roundtrip $Roundtrip)" @((Py "verify_all.py"), "--roundtrip", "$Roundtrip")
}

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "  done" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "  log: $log" -ForegroundColor Green
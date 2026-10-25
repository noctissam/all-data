# Three-line table extraction: PDF -> image -> Umi-OCR -> Excel

Takes a PDF, finds the three-line tables (三线表) by their vector rules, renders each
one **twice**, runs **Umi-OCR** on both copies, cross-checks the two extractions cell
by cell, and writes the result as plain grid tables in one Excel workbook.

Everything produced by this workspace lives under `NEW-TRY/`. Nothing outside it is
touched.

## Layout

    NEW-TRY/
      run_pipeline.ps1        one-command run
      src/common.py           paths + detection thresholds (CFG)
      src/s1_detect_tables.py locate three-line tables, render image A and image B
      src/s2_umi_ocr.py       Umi-OCR: A/B English (extract + verify), C Chinese (symbol donor)
      src/s3_verify_grid.py   rebuild the grid, diff A vs B, symbol repair
      src/s4_rescue_cells.py  600 dpi close-up of suspicious cells
      src/s5_to_excel.py      write the workbook
      out/
        tables.json           detected tables + geometry + per-page rules
        img/                  T01_p02_A.png / T01_p02_B.png  (same content, 2 renders)
        page_preview/         full pages with the candidate boxes drawn
        ocr/                  raw Umi-OCR json per pass per table
        grid/                 grid json + diff / lowconf / rescue csv per table
        log/                  one log per step
        tables_extracted.xlsx the workbook
      REPORT.md               result of the test run

## Run

    # from NEW-TRY
    .\run_pipeline.ps1 "..\2  Characterization of key odorants causing the roasted and mud-like aromas in.pdf"

or step by step:

    python src\s1_detect_tables.py "<pdf>"
    python src\s2_umi_ocr.py
    python src\s3_verify_grid.py
    python src\s4_rescue_cells.py
    python src\s5_to_excel.py

## How it works

**1. Detection is structural, not OCR-based.** A three-line table is three long thin
horizontal rules with no vertical rules. `s1` pulls every thin wide shape out of
`page.get_drawings()`, merges duplicates, and looks for a top / header / bottom triple.
Candidates then have to pass a tabularity gate - the rows between the header rule and
the bottom rule must mostly split into 3+ horizontally separated runs. That is what
rejects the decorative rules on a journal first page (ARTICLE INFO / ABSTRACT banner)
which otherwise look exactly like a table.

Long tables are flagged (`long_table`: height >= 150 pt or >= 8 data rows) but nothing
is dropped on that basis - every three-line table gets extracted, per your choice.

The crop is grown outwards until it hits blank space, so the caption above and the
footnotes below come out whole rather than sliced.

**2. Two images per table, same content.** `A` is the main pass at 300 dpi; `B` is an
independent re-render of the same crop at 400 dpi from a freshly opened document.
Different raster, identical content - so the two OCR runs make independent mistakes
and the comparison is worth something. Both file names, sizes and md5 hashes are
listed on sheet `92_图片清单`.

**3. OCR.** Umi-OCR Rapid 2.1.3 (`C:\UMI-OCR\Umi-OCR_Rapid_v2.1.3`) over its local
HTTP API on port 1224, `ocr.maxSideLen=999999` (no downscaling), `tbpu.parser=none`
and `data.format=dict` so the raw box geometry survives. Results are cached per image,
so a re-run only redoes what changed. Three passes:

| pass | image | model | role |
|---|---|---|---|
| A | `_A.png` 300 dpi | English | the extraction |
| B | `_B.png` 400 dpi | English | verification - independent render, independent errors |
| C | `_A.png` 300 dpi | Chinese | symbol donor only (see below) |

**4. Grid reconstruction.** Box coordinates are mapped back to PDF points and tagged
`caption` / `header` / `body` / `note` using the three detected rules. Then:

- each line is split into runs at gaps >= 4.5 pt;
- column separators are the x ranges that essentially no run reaches (up to 35% of the
  rows may bridge a gutter - group-label rows like "Lactones" do exactly that);
- lines cluster into rows by y; runs map onto columns; a run spanning several columns
  becomes a merged cell;
- pass B is rebuilt on its own geometry (structural check) **and** re-gridded onto pass
  A's columns, so the two extractions can be compared cell by cell.

Those two constants are the sensitive ones. They were chosen on the test PDF: with
4.5 pt / 35% all six tables get exactly the column count the printed table has.

**5. Verification.** Per cell: equal / equal-ignoring-spacing-and-dashes / conflict.
Conflicts take the higher-confidence reading and are written to `90_复核_差异` and
highlighted in the table sheet. Cells below `--conf` (default 0.80) go to
`91_复核_低置信`. Both passes' independent column counts are compared too.

## The symbol problem, and the two mechanisms that fix it

`dict_en.txt` is the English model's whole vocabulary: **94 entries, every one ASCII**.
μ, ±, γ and superscript-2 are not in it. The English pass therefore cannot produce them
at all - it emits a wrong lookalike instead (μ → `g`, ± → `+`, `*`, or nothing). The
Chinese model uses a 6623-entry dictionary that has all of them and reads them
correctly, but it is worse on Latin text (it drops footnote superscripts and turns
`γ-nonalactone` into `Y-nonalactone`).

The two failure modes are disjoint, so neither channel is trusted outright.

**Mechanism 1 - symbol donor (pass C, in `s3`).** A C reading replaces the A/B
consensus only when *all three* hold:

1. every character it introduces is in the whitelist
   `± µ μ γ β α δ θ ° ² ³ ≤ ≥ × ÷ ∞ ≠ ≈ ∓`;
2. the alphanumeric skeleton (all letters and digits, in order) is unchanged;
3. so pass C can never rewrite a word or a number.

The whitelist is not decoration. "Has a character dict_en lacks" is necessary but not
sufficient: pass C read the `<` of `<1` as U+039B GREEK CAPITAL LAMDA twice, which
passes the skeleton test and would have written Λ into a concentration column. Greek
capitals are excluded for exactly that reason. `--donor-chars` extends the list.

**Mechanism 2 - 600 dpi close-up (in `s4`).** At page scale the ± often never comes
back as its own box at all, so no model can recover it. Re-rendering *just that cell*
at 600 dpi puts the glyph where the detector can see it:

    page scale,  pass A : '717.6 38.8'          (the ± is simply gone)
    600 dpi crop, pass C: '717.6 ± 38.8'

600 dpi is the ceiling - at 1200 the detector starts splitting the cell and the reading
order reverses (`'4.6 301.5 +'`). Cells are selected when A and B disagreed, when
confidence is low, or when the text is shaped like `number <separator> number` with the
separator missing or an ASCII stand-in from `{+ * : = ~ H | ^ < > Λ}`.

Two guards keep the close-up from undoing the first mechanism, both of which actually
bit during development:

- the current value competes as a candidate, and any candidate spelling a whitelisted
  symbol beats one that does not, whatever the scores say - otherwise the English
  close-up outscores the page-level reading and a rescued ± is silently dropped again;
- on the score-based path the candidate must contain every non-space character of the
  current value, because `- 0.0005` → ` 0.0005` and `<1` → `Λ1` were both real
  regressions before that rule existed.

Every change is logged to `out/grid/<table>_rescue.csv`; symbol repairs to
`_diff.csv` with status `repaired_C`.

## Knobs

    s1:  --dpi-main 300 --dpi-check 400        CFG in src/common.py: rule widths,
                                               min_col_fill, long_h_pt, padding
    s2:  --lang English --lang-c 简体中文 --no-pass-c --max-side 999999 --restart
    s3:  --conf 0.80 --min-gap 4.5 --max-cover 0.35 --row-gap 0.55
        --min-col-fill 0.30 --donor-chars "<extra>"
    s4:  --dpi 600 --conf 0.80 --max-cells 400
    s5:  --out <path> --no-mark

## Known limits (found on the test PDF)

- **A cell the engine missed entirely is indistinguishable from an empty one.** A lone
  `-` that no pass picked up leaves a blank that reads as "not applicable" and lands in
  no review sheet. Not fixed by anything above - it needs a detection-side guarantee.
- **A table split across a page break** is extracted as two tables; there is no
  stitching yet. T02/T03 in the test run are the two halves of one logical table.
- **A cell that wraps onto a second visual line becomes a second row.** T05 has
  "Roasted/onion-like" and "3-(Methylthio)propanal" each split across two lines in the
  printed table, and they come out as two rows with the continuation in the next row's
  first cell. Row clustering keeps line spacing, so this is the expected behaviour, but
  it is a real structural loss. Stitching needs the fact that a wrapped line has fewer
  runs than the rows around it - not implemented.
- **Row-group labels** ("3-1", "6-2" in T05) sit in the first column with an empty
  second column, as printed. That is correct, just worth knowing before sorting.

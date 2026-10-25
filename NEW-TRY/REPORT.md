# Test run report

PDF: `2  Characterization of key odorants causing the roasted and mud-like aromas in.pdf`
(Food Research International, 13 pages, **no text layer** - every glyph is a vector
path, so OCR is not optional here)

Run: `.\run_pipeline.ps1 "<pdf>"`, all five steps clean, no failures.

## 1. Detection

7 rule-triples found across 13 pages, 1 rejected by the tabularity gate:

| page | what | verdict |
|---|---|---|
| 1 | three long rules spanning 402 pt | **rejected** - median 2.0 text runs per row, i.e. the ARTICLE INFO / ABSTRACT banner, not a table |
| 2, 4, 5, 10, 11, 12 | three-line tables | kept (T01-T06) |

6 tables kept, 5 of them long. Pages 3, 6, 7, 8, 9, 13 have no table.

## 2. Images

12 files, 2212-2950 px wide, from two independent renders of the same crop:

- `T0x_pNN_A.png` - 300 dpi, main pass
- `T0x_pNN_B.png` - 400 dpi, verification pass

md5 of each is on sheet `92_图片清单`. Content is identical by construction; the
resolution differs so the two OCR runs fail independently.

## 3. OCR

Umi-OCR Rapid 2.1.3, `maxSideLen=999999`, parser off, raw boxes kept. Three passes per
table: A and B in English (two independent renders), C in Chinese (symbol donor).
832 boxes in A, 989 in B, 852 in C. Cached on disk after the first run.

## 4. Grid + verification

| table | page | cols (A) | cols (B) | header rows | data rows | A/B agreement | conflicts | low-score | symbol fix | rescue |
|---|---|---|---|---|---|---|---|---|---|---|
| T01 | 2 | 6 | 6 | 2 | 16 | 83.3% | 18 | 10 | 4 | 18 |
| T02 | 4 | 11 | 11 | 3 | 6 | 93.9% | 6 | 4 | 1 | 3 |
| T03 | 5 | 7 | 7 | 3 | 60 | 86.8% | 58 | 52 | 108 | 7 |
| T04 | 10 | 7 | 7 | 2 | 18 | 99.3% | 1 | 6 | 1 | 0 |
| T05 | 11 | 5 | 5 | 2 | 14 | 100.0% | 0 | 0 | 0 | 0 |
| T06 | 12 | 7 | 7 | 2 | 4 | 100.0% | 0 | 0 | 1 | 0 |

Both English passes independently produced the same column count on all six tables -
the structural reading is stable. 0 one-sided cells, meaning no row or cell exists in
one pass and not the other.

**83 conflicts before repair, and 81 of them were the ± symbol**, not a digit:

    pass A: 622,200  1786
    pass B: 622,200 + 1786

Same digits, different reading of the one glyph between them. It lands in the
concentration columns (T03 cols 4-5: 54 of 58) and in the sample-abbreviation column of
T01, where it is a hyphen: `LZ21(14)` vs `LZ-21(14)`.

The two real disagreements are both in T03 and both look like OCR noise rather than a
structural error:

    row 33 col 3:  91.0d  vs  91.od      (footnote marker d vs the letter o)
    row 44 col 4:  114  9  vs  114 *     (pass B dropped the 9)

Concentration of conflicts by column:

    T01 col2 (sample abbrev)  8    T03 col4 (conc. LZ)  30
    T01 col4 (mean conc.)    10    T03 col5 (conc. GJ)  24
    T02 col1/2/7/8           6    T03 col3/6/7         4
    T04 col3                  1

So: hyphen and ±, concentrated exactly where you would expect.

## 4b. Symbol repair and cell rescue

The 83 conflicts above are what a two-pass check finds on its own. Two further
mechanisms were added after seeing that μ and ± were simply not in `dict_en.txt`
(94 entries, all ASCII - the English model cannot spell them at all).

**Pass C, Chinese symbol donor** - adopted only where the alphanumeric skeleton is
unchanged and every introduced character is whitelisted. 115 cells fixed: 109 ±, 5 μ,
1 ≥. Zero repairs touched a digit or a letter (verified by re-deriving the skeleton of
all 115 before/after pairs).

    T03 '7,606,936  17,161'  ->  '7,606,936 ± 17,161'
    T03 'Concentrations (g/L)'  ->  'Concentrations (μg/L)'
    T04 'FD factor (FD  9)'  ->  'FD factor (FD ≥ 9)'      (checked against the image)

**600 dpi close-up** - 28 cells changed: 19 where the ± had vanished entirely at page
scale, and 9 by score among close-up readings.

    '717.6 38.8'   ->  '717.6 ± 38.8'
    '1903207'      ->  '1903 ± 207'
    '0.0032'       ->  '-0.0032'
    '0.0090.09'    ->  '0.009-0.09'
    'LZ21(14)'     ->  'LZ-21(14)'

Residual after both: **0** cells shaped `number ? number` still lack the ±, and **0**
units read `g/L` where the source has μ. (The one `g/L` left in T02 is `Range (mg/L)` -
milligrams, which is what the paper says.)

Three regressions were caught and fixed while building this, all of them worth
recording because they are the failure modes to expect:

| regression | why it passed the naive rule | guard |
|---|---|---|
| `<1` → `Λ1` | Λ is outside dict_en and the skeleton `1` matches | donor whitelist excludes Greek capitals |
| `- 0.0005` → ` 0.0005` | the losing reading outscored the correct one | score path requires a character superset |
| `1552.0 ± 91.2` → `1552.0  91.2` | close-up candidates were compared without the current value | current value competes; donor symbols are preferred over their absence |

## 5. What is in the workbook

`out/tables_extracted.xlsx`, sheets:

- `00_索引` - source PDF, engine, all DPIs, one row per table with agreement and every
  review counter
- `T01_p02` ... `T06_p12` - caption, header rows (spanning cells merged), data rows,
  footnote. Conflicting cells shaded orange, low-score cells shaded yellow, freeze panes
  below the header.
- `90_复核_差异` - 198 rows: 83 A/B disagreements + 115 symbol repairs
- `91_复核_低置信` - 72 rows below 0.80
- `92_符号修补` - the 115 symbols pass C supplied
- `93_单元格抢救` - the 28 cells the 600 dpi pass changed, with before/after and all
  close-up readings
- `94_图片清单` - the 12 images with byte size, dpi and md5

## 6. Honest assessment before you use the numbers

**A cell the engine missed entirely is still indistinguishable from an empty one.** A
lone `-` that no pass picked up leaves a blank that reads as "not applicable" and lands
in no review sheet. Neither mechanism helps, because the suspicion rules key on text
that is there. That is the main remaining hole.

Everything else is now covered by the review sheets, but two of them need you to know
what you are looking at:

- `90_复核_差异` mixes two very different things - 83 unresolved A/B disagreements and
  115 repairs that were applied. Filter on the status column.
- `91_复核_低置信` lists cells *after* repair, so a repaired ± cell appears there with
  its corrected text and the low score that triggered the review. It is not a claim
  that the current value is wrong.

Also structural, and visible in the output above:

- **T02 and T03 are `(continued)` halves of one logical table** - this PDF splits it
  across pages 3-5 and the pipeline reports the halves as T02 / T03 without stitching.
- **Header cells that wrap** ("Quantified ion (m/z)", "Aroma compounds") become a
  second header row.
- **Body cells that wrap** are worse: T05's "Roasted/onion-like" and
  "3-(Methylthio)propanal" each span two printed lines, and they come out as two rows
  with the continuation sitting in the first cell of the next row (`like`, `propanal`).
  Same for the T05 footnote, where a footnote line was split across two rows.
  Row clustering uses line spacing, so a wrapped cell is indistinguishable from a short
  row at this stage.

## 7. Reproducing

    cd NEW-TRY
    .\run_pipeline.ps1 "..\2  Characterization of key odorants causing the roasted and mud-like aromas in.pdf"

Second run took 0 s for OCR (cache) and a couple of minutes for the rest, most of it in
the 600 dpi rescue. `-RestartOcr` forces fresh OCR, `-RestartAll` clears everything
first.

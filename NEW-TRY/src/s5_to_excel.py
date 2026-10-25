# -*- coding: utf-8 -*-
"""
Step 5 - write the extracted three-line tables into one Excel workbook.

Sheets
    00_索引        source file, settings, one row per table, agreement + review counters
    T01_p02 ...    one sheet per table: caption / header rows / body rows / note,
                   as a plain grid.  Spanning header cells stay merged.
    90_复核_差异    every cell where pass A and pass B disagree
    91_复核_低置信  every cell whose OCR confidence is below the threshold
    92_符号修补    symbols pass C supplied that the English model cannot spell
    93_单元格抢救  cells changed by the 600 dpi close-up pass
    94_图片清单    the two images per table (size / dpi / md5) as evidence for the double pass

Usage:
    python src/s5_to_excel.py [--out tables_extracted.xlsx] [--no-mark]
"""

import argparse
import csv
import hashlib
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from common import GRID_DIR, IMG_DIR, LOG_DIR, OUT, UMI_EXE, load_json, load_tables, log  # noqa: E402

HEAD_FILL = PatternFill("solid", fgColor="EDEDED")
CAP_FONT = Font(bold=True, size=11)
HEAD_FONT = Font(bold=True)
NOTE_FONT = Font(italic=True, size=9, color="555555")
DIFF_FILL = PatternFill("solid", fgColor="FCE4D6")     # A/B disagreement
LOW_FILL = PatternFill("solid", fgColor="FFF2CC")      # low OCR confidence
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.reader(f))[1:]


def width_for(text):
    """Rough column width in characters."""
    return max(6, min(46, int(len(str(text)) * 1.05) + 2))


def write_table_sheet(wb, g, diffs, lows, mark):
    ws = wb.create_sheet(g["name"])
    ncol = g["n_col"]
    r = 1

    diff_cells = {(int(x[4]), int(x[5])): x for x in diffs if x[3] in ("head", "body")}
    low_cells = {(int(x[4]), int(x[5])): x for x in lows if x[3] in ("head", "body")}

    if g["caption"]:
        ws.cell(row=r, column=1,
                value=" ".join(x for x in g["caption"] if x)).font = CAP_FONT
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=max(ncol, 2))
        r += 1
    if g.get("long_table") is not None:
        ws.cell(row=r, column=1,
                value="%s | PDF p.%d | %d cols x %d data rows | %s | A图 %s | B图 %s"
                      % (g["id"], g["page"], ncol, g["n_body_row"],
                         "long table" if g["long_table"] else "short table",
                         os.path.basename(g["img_a"]),
                         os.path.basename(g["img_b"]))).font = NOTE_FONT
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=max(ncol, 2))
        r += 1
    r += 1

    head_start = r
    for sec, rows in (("head", g["header"]), ("body", g["body"])):
        for row in rows:
            c = 0
            for cell in row:
                span = cell["span"]
                cc = c + 1
                if span >= 0:
                    rr = r
                    cv = ws.cell(row=rr, column=cc, value=cell["text"])
                    cv.border = BOX
                    cv.alignment = Alignment(vertical="center", wrap_text=False)
                    if sec == "head":
                        cv.font = HEAD_FONT
                        cv.fill = HEAD_FILL
                    if mark and (rr, c) in diff_cells:
                        cv.fill = DIFF_FILL
                    elif mark and (rr, c) in low_cells:
                        cv.fill = LOW_FILL
                    if span > 1:
                        ws.merge_cells(start_row=rr, start_column=cc,
                                       end_row=rr, end_column=cc + span - 1)
                c += 1
            for k in range(c, ncol):
                ws.cell(row=r, column=k + 1).border = BOX
            r += 1

    if g["note"]:
        r += 1
        for n in g["note"]:
            ws.cell(row=r, column=1, value=n).font = NOTE_FONT
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=max(ncol, 2))
            r += 1

    widths = [8] * ncol
    for row in g["header"] + g["body"]:
        for c, cell in enumerate(row):
            if cell["span"] < 0 or c >= ncol:
                continue
            widths[c] = max(widths[c], width_for(cell["text"]))
    for i, w in enumerate(widths):
        ws.column_dimensions[get_column_letter(i + 1)].width = w
    ws.freeze_panes = ws.cell(row=head_start + len(g["header"]), column=1)
    return ws


def write_index(wb, db, grids, imgs):
    ws = wb.create_sheet("00_索引")
    m = db["meta"]
    head = [("源 PDF", os.path.basename(m["pdf"])),
            ("完整路径", m["pdf"]),
            ("页数", m["n_pages"]),
            ("候选三线表结构 / 通过表格性检验",
             "%d / %d" % (m["n_candidates"], m["n_tables"])),
            ("长表 / 全部表", "%d / %d" % (m["n_long"], m["n_tables"])),
            ("OCR 引擎", UMI_EXE),
            ("A 通道 dpi", m["dpi_main"]),
            ("B 通道 dpi (复核)", m["dpi_check"]),
            ("导出时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))]
    r = 1
    for k, v in head:
        ws.cell(row=r, column=1, value=k).font = HEAD_FONT
        ws.cell(row=r, column=2, value=v)
        r += 1
    r += 1

    cols = ["表号", "PDF 页", "表标题", "列数", "表头行", "数据行", "长表",
            "A/B 单元格一致率", "差异", "低置信", "符号修补", "特写抢救",
            "B 通道独立列数", "主图 (A)", "复核图 (B)", "工作表"]
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=r, column=i, value=c)
        cell.font = HEAD_FONT
        cell.fill = HEAD_FILL
        cell.border = BOX
    hdr = r
    r += 1
    for g in grids:
        v = g["verify"]
        row = [g["id"], g["page"], g["caption_text"], g["n_col"], g["n_head_row"],
               g["n_body_row"], "是" if g["long_table"] else "否",
               "%.1f%%" % v["agree_pct"], v["n_conflict"], v["n_lowconf"],
               v.get("n_repaired", 0), v.get("n_rescued", 0),
               g["pass_b"]["n_col"], os.path.basename(g["img_a"]),
               os.path.basename(g["img_b"]), g["name"]]
        for i, val in enumerate(row, 1):
            ws.cell(row=r, column=i, value=val).border = BOX
        r += 1
    for i, w in enumerate([8, 7, 58, 7, 8, 8, 6, 16, 8, 9, 10, 10,
                           15, 18, 18, 12], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=hdr + 1, column=1)
    return ws


def write_sheet_from_rows(wb, title, header, rows, widths):
    ws = wb.create_sheet(title)
    for i, c in enumerate(header, 1):
        cell = ws.cell(row=1, column=i, value=c)
        cell.font = HEAD_FONT
        cell.fill = HEAD_FILL
        cell.border = BOX
    for r, row in enumerate(rows, 2):
        for i, val in enumerate(row, 1):
            ws.cell(row=r, column=i, value=val).border = BOX
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=2, column=1)
    return ws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUT, "tables_extracted.xlsx"))
    ap.add_argument("--no-mark", action="store_true",
                    help="do not colour the cells that failed verification")
    a = ap.parse_args()
    mark = not a.no_mark

    logfile = os.path.join(LOG_DIR, "s4_excel.log")
    log("STEP 4 - write excel", logfile)

    db = load_tables()
    grids = []
    all_diffs, all_lows, all_resc = [], [], []
    for t in db["tables"]:
        p = os.path.join(GRID_DIR, "%s_grid.json" % t["name"])
        if not os.path.exists(p):
            log("  %s no grid json - skipped" % t["id"], logfile)
            continue
        grids.append(load_json(p))
        all_diffs += read_csv(os.path.join(GRID_DIR, "%s_diff.csv" % t["name"]))
        all_lows += read_csv(os.path.join(GRID_DIR, "%s_lowconf.csv" % t["name"]))
        all_resc += read_csv(os.path.join(GRID_DIR, "%s_rescue.csv" % t["name"]))
    sym_rows = [r for r in all_diffs if r[6] == "repaired_C"]

    imgs = []
    for t in db["tables"]:
        for key in ("img_a", "img_b"):
            p = os.path.join(IMG_DIR, os.path.basename(t[key]))
            imgs.append([t["id"], t["page"], "主提取 A" if key == "img_a" else "复核 B",
                         os.path.basename(p), os.path.getsize(p),
                         db["meta"]["dpi_main"] if key == "img_a" else db["meta"]["dpi_check"],
                         md5(p), t["name"]])

    wb = Workbook()
    wb.remove(wb.active)
    write_index(wb, db, grids, imgs)
    for g in grids:
        write_table_sheet(wb, g,
                          read_csv(os.path.join(GRID_DIR, "%s_diff.csv" % g["name"])),
                          read_csv(os.path.join(GRID_DIR, "%s_lowconf.csv" % g["name"])),
                          mark)
    write_sheet_from_rows(wb, "90_复核_差异",
                          ["表号", "名称", "PDF页", "区", "行", "列", "状态",
                           "A 通道文本", "B 通道文本", "最低置信度"],
                          all_diffs, [8, 14, 7, 6, 5, 5, 12, 34, 34, 12])
    write_sheet_from_rows(wb, "91_复核_低置信",
                          ["表号", "名称", "PDF页", "区", "行", "列",
                           "采用文本", "置信度", "状态"],
                          all_lows, [8, 14, 7, 6, 5, 5, 34, 10, 12])
    write_sheet_from_rows(wb, "92_符号修补",
                          ["表号", "名称", "PDF页", "区", "行", "列", "状态",
                           "A/B 采用文本", "C 通道文本", "最低置信度"],
                          sym_rows, [8, 14, 7, 6, 5, 5, 12, 34, 34, 12])
    write_sheet_from_rows(wb, "93_单元格抢救",
                          ["表号", "名称", "PDF页", "区", "行", "列",
                           "可疑原因", "处理", "改前", "改后", "特写读数"],
                          all_resc, [8, 14, 7, 6, 5, 5, 12, 13, 26, 26, 46])
    write_sheet_from_rows(wb, "94_图片清单",
                          ["表号", "PDF页", "通道", "文件名", "字节", "dpi", "md5", "工作表"],
                          imgs, [8, 7, 10, 20, 12, 6, 34, 12])

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    try:
        wb.save(a.out)
    except PermissionError:
        raise SystemExit(
            "cannot write %s\n"
            "The workbook is open in Excel - close it (or use --out to write a copy) "
            "and run this step again. Everything upstream is already saved."
            % a.out)
    log("  tables: %d  diff: %d  lowconf: %d  symbol-repair: %d  rescue: %d" % (
        len(grids), len(all_diffs), len(all_lows), len(sym_rows), len(all_resc)), logfile)
    log("  -> %s" % a.out, logfile)
    log("  sheets: %s" % ", ".join(wb.sheetnames), logfile)


if __name__ == "__main__":
    main()

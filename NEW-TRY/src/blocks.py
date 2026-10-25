# -*- coding: utf-8 -*-
"""
Find the 基础数据 blocks in a built worksheet.

Five scripts read the workbook and all five were identifying a data block the same way:
column A of some row reads 化合物名称. That is not sufficient, because 化合物名称 also
appears as an ordinary header row inside the 原表逐格 block, which holds every extracted
cell verbatim. Reading from there gave 87 rows in which the second column was a
concentration rather than a CAS, and 42 rows in which the "compound name" was a row index.

A 基础数据 block is written by one function, and that function always emits CAS号 in the
column after the name. Requiring both is a property of the writer rather than a guess
about the layout, so it holds for every sheet including ones not yet seen.

Use:  blocks = find_data_blocks(rows);  for start, stop in blocks: ...
"""

import re

NAME_HEAD = re.compile(r"^\s*化合物名称")
CAS_HEAD = re.compile(r"^\s*CAS")

# A block ends at the next caption or section marker. 条 is here because the verbatim
# caption reads "——— 以下为原表逐格内容 ———".
BLOCK_END = re.compile(
    r"^\s*(文献|表单|校验|表\s*\d|—|⚠|序号|化合物名称|CAS号)"
    r"|^\s*原表逐格|^\s*基础数据"
    r"|^\s*(序号|表|Table)\b.*\S{12,}")


def is_data_header(row):
    """A 基础数据 header row: the name column and the CAS column are both present."""
    if not row:
        return False
    a = str(row[0] or "")
    if not NAME_HEAD.match(a):
        return False
    for c in row[1:4]:
        if c is not None and CAS_HEAD.match(str(c).strip()):
            return True
    return False


def find_data_blocks(rows):
    """
    Yield (header_index, stop_index) for each 基础数据 block. stop_index is exclusive.

    Only a 化合物名称 row that is not followed by the row after it means the block is the
    verbatim one, so is_data_header is the whole test.
    """
    starts = [i for i, row in enumerate(rows) if is_data_header(row)]
    for k, s in enumerate(starts):
        stop = starts[k + 1] if k + 1 < len(starts) else len(rows)
        for r in range(s + 1, stop):
            a0 = str(rows[r][0] or "") if rows[r] else ""
            if not a0.strip():
                continue
            if BLOCK_END.match(a0):
                stop = r
                break
        yield s, stop
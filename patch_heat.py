# -*- coding: utf-8 -*-
"""把 heat_block.py 替换进 analyze_pca.py 的聚类热图段"""
import io
base = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
p = base + r"\analyze_pca.py"
s = io.open(p, encoding="utf-8").read()
blk = io.open(base + r"\heat_block.py", encoding="utf-8").read()
a = s.index("# ---------------- 聚类热图")
b = s.index("# ---------------- 补充: 相对组成PCA")
s2 = s[:a] + blk + s[b:]
# 去掉后面重复的 fcluster 局部导入(块内已导入)
s2 = s2.replace('from scipy.cluster.hierarchy import fcluster\ncl = fcluster',
                'cl = fcluster')
io.open(p, "w", encoding="utf-8").write(s2)
print("spliced, len", len(s), "->", len(s2))

# -*- coding: utf-8 -*-
import io
import os

p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "50_make_deck.py")
t = io.open(p, encoding="utf-8").read()
subs = [
    ("这些结论在多数篇独立文献中同向出现，而非单一数据集的偶然相关",
     "这些结论在多篇独立文献中同向出现，而非单一数据集的偶然相关"),
    ("tf = panel(s, L, 3.68, CW, 1.86, fill=RED_BG, line=ACCENT, line_w=1.4, pad=0.24,",
     "tf = panel(s, L, 3.62, CW, 1.62, fill=RED_BG, line=ACCENT, line_w=1.4, pad=0.24,"),
    ("tf = panel(s, L, 5.70, CW, 1.06, fill=GREEN_BG, line=GREEN, pad=0.22)",
     "tf = panel(s, L, 5.44, CW, 1.32, fill=GREEN_BG, line=GREEN, pad=0.22)"),
    ("tb, tf = textbox(s, L + 0.22, 3.40, CW - 0.44, 1.06)",
     "tb, tf = textbox(s, L + 0.22, 3.46, CW - 0.44, 0.98)"),
]
for a, b in subs:
    assert a in t, a[:60]
    t = t.replace(a, b, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(t)
print("applied", len(subs), "substitutions")

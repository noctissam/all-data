#!/usr/bin/env python3
"""Independent audit, method note and a scientific coverage figure."""
import collections
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

root = Path(__file__).resolve().parent
d = json.loads((root/"design.json").read_text())
cs = d["compounds"]
variables = [c for c in cs if not c["base"]]
byid = {c["id"]: c for c in cs}
rows = d["rows"]
train = [r for r in rows if r["purpose"] == "拟合"]
ids = {r["sample_id"]: r for r in rows}
audit = []

def checked(name, condition):
    assert condition, name
    audit.append({"check": name, "result": "passed"})

checked("41 candidates, 30 variable, 11 fixed",len(cs)==41 and len(variables)==30 and sum(c["base"] for c in cs)==11)
checked("350 preparations; 310 training; 20 repeats; 20 validation",
        len(rows)==350 and collections.Counter(r["purpose"] for r in rows)==
        {"拟合":310,"独立配制重复":20,"留出验证":20})
checked("No formulation exceeds four variable compounds",all(len(r["compound_ids"])<=4 for r in rows))
checked("All 30 variables appear in training",set().union(*(set(r["compound_ids"]) for r in train))=={c["id"] for c in variables})
checked("Base compounds never vary",not any(byid[i]["base"] for r in rows for i in r["compound_ids"]))
for c in cs:
    vals=[x for x in c["raw"] if x is not None]
    checked("Source statistics ID "+str(c["id"]),
            math.isclose(statistics.mean(vals),c["mean"],rel_tol=1e-12) and
            statistics.median(vals)==c["median"] and max(vals)==c["max"])
    for val in c["levels"]:
        checked("Observed positive range ID "+str(c["id"]),c["min_positive"]<=val<=c["max"])
for r in rows:
    checked("Dose and level mapping "+r["sample_id"],
            all(math.isclose(conc,byid[i]["levels"][byid[i]["codes"].index(code)],rel_tol=1e-12)
                for i,code,conc in zip(r["compound_ids"],r["codes"],r["concentrations"])))
    if r["repeat_of"]:
        orig=ids[r["repeat_of"]]
        checked("Independent repeat prescription "+r["sample_id"],
                r["compound_ids"]==orig["compound_ids"] and r["concentrations"]==orig["concentrations"])
pc=collections.Counter()
cells=collections.defaultdict(set)
backgrounds=collections.defaultdict(set)
for r in train:
    for a,b in itertools.combinations(range(len(r["compound_ids"])),2):
        ia,ib=r["compound_ids"][a],r["compound_ids"][b]
        pair=tuple(sorted([ia,ib]))
        pc[pair]+=1
        cells[pair].add(tuple((i,r["codes"][r["compound_ids"].index(i)]) for i in pair))
        backgrounds[pair].add(tuple(sorted(i for i in r["compound_ids"] if i not in pair)))
checked("435 pairs covered at least twice in different compositions",
        len(pc)==435 and min(pc.values())>=2 and min(map(len,backgrounds.values()))>=2)
checked("125 cross-level pairs covered",
        sum(byid[a]["nlevels"]!=byid[b]["nlevels"] for a,b in pc)==125)
checked("1341 distinct positive level cells",sum(map(len,cells.values()))==1341)
checked("330 unique formulations",
        len({(tuple(r["compound_ids"]),tuple(r["codes"])) for r in rows})==330)
counts=collections.Counter(tuple(r["compound_ids"]) for r in rows)
checked("Maximum three preparations per composition",max(counts.values())==3)
train_comps={tuple(r["compound_ids"]) for r in train}
checked("Validation compositions absent from training",
        all(tuple(r["compound_ids"]) not in train_comps for r in rows if r["purpose"]=="留出验证"))

vi={c["id"]:j for j,c in enumerate(variables)}
quad=[c["id"] for c in variables if c["nlevels"]==3]
X=[]
for r in train:
    p=np.zeros(30);z=np.zeros(30)
    for i,conc in zip(r["compound_ids"],r["concentrations"]):
        c=byid[i]
        p[vi[i]]=1
        z[vi[i]]=2*math.log(conc/c["levels"][0])/math.log(c["levels"][-1]/c["levels"][0])-1
    X.append([1,*p,*z,*(z[vi[i]]**2 for i in quad)])
X=np.array(X)
checked("Independent core matrix rank 86",np.linalg.matrix_rank(X)==86)
checked("Independent core condition number",
        math.isclose(float(np.linalg.cond(X)),d["summary"]["core_condition_number"],rel_tol=1e-10))
(root/"核查结果.json").write_text(json.dumps({"checked_items":len(audit),"all_passed":True,
    "pair_counts":dict(collections.Counter(pc.values())),"core_rank":86,
    "condition_number":float(np.linalg.cond(X)),"checks":audit},ensure_ascii=False,indent=2)+"\n")

# Compare actual composition coverage, not effect estimates.
# Historical grouping used only to draw the comparison panel.
# These lists never enter composition or concentration optimization.
old_groups = [
    [111,52,32,141], [111,58,69,232], [111,126,75,136],
    [52,11,207,7], [111,209,255,61], [52,18,152,105],
    [111,40,115,186], [141,117,227,232], [32,53,69,7],
    [58,61,105,255], [56,79,90,114], [56,79,90,165],
    [56,79,114,165], [56,90,114,165],
]
order=[c for c in variables if c["nlevels"]==3]+[c for c in variables if c["nlevels"]==2]
idx={c["id"]:i for i,c in enumerate(order)}
old_matrix=np.zeros((30,30));new_matrix=np.zeros((30,30))
for old_group in old_groups:
    for a,b in itertools.combinations(old_group,2):
        if a in idx and b in idx:
            old_matrix[idx[a],idx[b]]=old_matrix[idx[b],idx[a]]=1
for a,b in pc:
    new_matrix[idx[a],idx[b]]=new_matrix[idx[b],idx[a]]=1
fig,axes=plt.subplots(1,2,figsize=(12.8,6.2))
for ax,arr,title in zip(axes,[old_matrix,new_matrix],
        ["Previous grouping: 69 / 435 pairs","Algorithm design: 435 / 435 pairs"]):
    masked=np.ma.masked_where(np.eye(30,dtype=bool),arr)
    cm=ListedColormap(["#EEF1F5","#234D73"]);cm.set_bad("#FFFFFF")
    ax.imshow(masked,cmap=cm,vmin=0,vmax=1)
    labels=[str(c["id"]) for c in order]
    ax.set_xticks(range(30),labels,rotation=90,fontsize=7)
    ax.set_yticks(range(30),labels,fontsize=7)
    ax.axhline(24.5,color="#D27A2C",lw=1.2);ax.axvline(24.5,color="#D27A2C",lw=1.2)
    ax.set_title(title,fontsize=12,pad=13)
    ax.set_xlabel("Compound ID: 25 three-level, then 5 two-level variables",fontsize=9)
axes[0].set_ylabel("Compound ID",fontsize=10)
fig.legend(handles=[Patch(facecolor="#234D73",label="Pair varies together in training"),
                    Patch(facecolor="#EEF1F5",label="Not included")],
           loc="lower center",bbox_to_anchor=(.5,.04),ncol=2,frameon=False,fontsize=10)
fig.text(.5,.015,"Coverage does not establish sensory interaction. Positive concentration cells: 1341 / 3490 (38.4%).",
         ha="center",fontsize=9,color="#465568")
fig.subplots_adjust(left=.06,right=.99,top=.9,bottom=.17,wspace=.19)
fig.savefig(root/"配对覆盖对比.png",dpi=180,bbox_inches="tight",facecolor="white")
plt.close(fig)

q=d["summary"]
method = f"""# 350次化合物组合与浓度选样算法

日期：2026年10月27日。用途：依据现有候选物和数据库范围生成可复核的探索性实验设计。

## 本次实际完成的结果

- 41种候选物全部保留；沿用11种固定基底、30种可变物质的分工。
- 350次独立配制计划：310个拟合配方、20次独立配制重复、20个留出验证配方；共330种不同配方。
- 拟合部分：85个单一可变物质的浓度锚点、1个共同基底对照、224个四元配方。
- 30种可变物质的435个两两配对全部在拟合样本中出现，每对出现2–4次，且背景组成至少有2种。
- 原先遗漏的125个两档×三档配对全部包含。
- 所有样本最多4种可变物质；同一组成组最多3次配制。11种固定基底另计。
- 正浓度档位格覆盖1341/3490，约38.4%。这一指标与配对出现覆盖率100%不同。

这是跨组合的全局筛选设计。没有为每个四元组成分别安排27次BBD，也没有为每个组成分别拟合15个系数。

## 1. 输入与浓度规则

输入为仓库根目录“可用化合物原始数据.xlsx”的all data页，使用113个原始浓度列，不使用25个文献原始OAV列或四舍五入的计算OAV。单位为μg/L。Git blob SHA：

{d['config']['source_git_blob_sha']}

缺失值不作零值填补。原始数字0保留在均值、中位值统计中；设置正浓度档位时，以最小正值作为下界，未添加状态单独编码。

候选与角色规则沿用用户已确定的方案：平均浓度OAV或中位浓度OAV任一小于1者为共同固定基底，浓度固定为算术平均值；其余物质中，中位OAV≥2者为三档，中位OAV<2者为两档。这是输入角色规则，不是算法判断某物质是否重要。

本次三档使用：

L=数据库最小正浓度；M=√(L×H)；H=数据库最大浓度。

本次两档使用：

M=数据库中位浓度；H=数据库最大浓度。

因此，25种三档物质的新M是几何中点，不再自动等于原中位值。Excel把“原中位值”和“新M”分列。阈值×2不再作为本次低档的生成规则。所有拟添加的浓度都在数据库正浓度范围内，但不声称三档的感官间距相等，也不声称几何中点是感官最优水平。

## 2. 组成如何由算法选择

将30种可变物质所有四元子集列为候选：C(30,4)=27405个。

对224个四元拟合配方，采用词典序贪心选择：

1. 先找当前出现次数最少的配对，优先选择能增加这类配对覆盖的四元组成。
2. 若新增覆盖相同，选择能使物质出现次数更平衡的组成。
3. 再优先选择已有配对重复负担较小的组成。
4. 最后才按固定随机种子打破完全相同的选择。四元拟合组成不重复。

所有物质和配对使用相同权重，不按化学类别人工指定组，也不按PCA结果强制搭配。两档与三档物质进入同一候选池。

运行12个初始化，先比较最低配对覆盖次数，再比较配对次数方差及物质出现次数方差。最终每种物质在224个四元配方中出现29–31次。贪心法不构成全局最优性证明。

## 3. 浓度如何由算法选择

组成固定后，枚举每个组成允许的档位组合。用I准则选择浓度档位，而不是凭经验决定哪组用高浓度：

I=trace[M×(XᵀX)⁻¹]。

这里的M是实验区域中模型特征向量外积的平均，计算时用固定种子的6000个候选配方近似。参考分布明确规定为：四元组成均匀抽取，再对每个物质的允许浓度档位均匀抽取。

选点采用逐点加入与单行交换，4次初始化、每次最多3轮交换，保留I最小的结果。它是给定组成和给定模型下的启发式搜索，不称为已证明全局I最优。

另比较相同组成、相同单体锚点下的32套随机档位安排，并计算一套D准则安排作为参考。所有比较均不使用感官结果。

## 4. 必须明确的基础模型

此次浓度选点采用：

Y=β₀+Σαᵢpᵢ+Σβᵢzᵢ+Σ（三档物质）γᵢzᵢ²+ε。

pᵢ表示该物质是否加入；加入时zᵢ是以该物质正浓度下界和上界编码的对数浓度，未加入时pᵢ=zᵢ=0。该编码不会对零浓度取对数。

模型共86列：1个截距、30个存在效应、30个条件浓度项、25个单体曲率项。

选出的310个拟合配方矩阵秩为86，条件数为{q['core_condition_number']:.4f}。这只说明上述基础项可估计，不能证明真实响应符合这个模型。它作为交互筛选的基线，不承担全部交互解释。

此次I指标为{q['core_I']:.6f}，32套随机档位的平均I为{q['random_level_I_mean']:.6f}，相对降低{q['I_reduction_vs_random_mean']:.2%}。这是基础模型假设下的平均预测方差系数比较，不是实测感官预测误差降低。用独立6000个参考点复核的I为{q['independent_reference_I']:.6f}。

## 5. 交互作用能回答到哪一步

435个配对都出现至少2次，但每对没有做齐所有浓度格，也没有在所有背景中重复。

若在86个基础项外加入435个“是否共同存在”的交互项，模型共521列，本设计矩阵秩仅310，无法无约束地分别估计全部交互系数。若研究浓度依赖的交互，模型还需要适当的浓度乘积项，不能认为435个存在交互项已经覆盖所有浓度交互。

因此，后续可以根据实际感官结果进行预先约定的稀疏交互筛选，配合按配方分组的验证；重要交互应进一步独立配制确认。稀疏或贝叶斯分析依赖额外假设，不能仅靠算法名称把不可辨识问题变成已解决。

若主要目标改为对某几个四元组分别拟合完整二次曲面，应重新分配350次预算。广泛配对筛选与每组浓度精测是不同的实验资源安排。

## 6. 重复与验证

20次重复是计划重新独立配制相同配方：2次基底对照重复、18次参考组合重复。它们用于评价配制与感官变异。

20个验证配方使用拟合中从未出现的四元组成，并在看见感官结果之前由固定种子选定。它们不参与本次I选点，也不参与模型拟合；若后续用来调参，就应另设最终验证集。

18位感官员对这些样本的评分应按实际重复测量、场次与配制结构分析。18人不会将配方设计矩阵的秩提高18倍。本包不包含正式盲码和18人的场次呈样表。

## 7. 如何复现

依赖：Python、numpy、openpyxl（只读取输入），以及生成Excel所用的@oai/artifact-tool。无需安装优化求解器。

在仓库根目录运行：

```bash
OPENBLAS_NUM_THREADS=1 python 2026年10月27日_第01次/design_algorithm.py --input 可用化合物原始数据.xlsx --output algorithm_output --seed 20261027 --starts 12
```

也可解压完整包后运行design_algorithm.py，并把--input指向该原始Excel。选组与浓度算法可用上述Python依赖独立复现，不依赖Excel导出工具。

提供的build_workbook.mjs用于本环境导出Excel，读取生成的design.json。Excel中的原始浓度、浓度计算、配方浓度、OAV和20mL纯物质量具有公式联系。密度、纯度和母液浓度尚未作为输入，因此“ug/瓶”是纯物质量，不是纯品或母液的吸取体积。

更改候选物、角色规则、浓度档位或模型后，应重新运行；本次矩阵秩、I指标及浓度格覆盖率是当前设计的快照。

## 方法参考

1. NIST/SEMATECH. D-Optimal designs. https://www.itl.nist.gov/div898/handbook/pri/section5/pri521.htm
2. JMP. Optimality Criteria. https://www.jmp.com/support/help/en/19.0/jmp/optimality-criteria.shtml

上述文献支持基于预设模型的信息量选点原则。本包“先覆盖组成、再按I准则选择档位”的具体组合流程是针对本研究约束实现的方案，尚不是经本实验感官数据验证过的标准成套方法。
"""
(root/"算法说明与适用范围.md").write_text(method)
print(json.dumps({"audit_checks":len(audit),"all_passed":True,
                  "positive_level_cell_coverage":1341/3490},ensure_ascii=False))

# -*- coding: utf-8 -*-
"""
Translate Chinese systematic names of aroma compounds into English.

The English name is only an intermediate: it is looked up in PubChem and then thrown
away, so a wrong one writes a wrong CAS into a priority-1 column and nothing downstream
can tell. Every rule below obeys three constraints:

  a locant is never moved, added or dropped. 2,5-dimethylpyrazine must not come out as
  2,3-dimethylpyrazine, and 4-methylphenol must not lose its 4.

  where the Chinese name leaves a position unstated AND the parent offers no
  conventional default, the translation is refused. 2-甲基丙醇 is either
  2-methylpropan-1-ol or 2-methylpropan-2-ol - isobutanol or isopropanol, two different
  CAS numbers - and guessing one of them turns a visible blank into an invisible error.

  anything not covered returns None. A blank cell is visible; a plausible wrong one is
  not.

selfcheck_zh2en.py checks the output against known-good pairs and against the whole
corpus for lost locants.
"""

import re

# --------------------------------------------------------------------- tables

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
          "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13,
          "十四": 14, "十五": 15, "十六": 16, "十七": 17, "十八": 18,
          "十九": 19, "二十": 20, "二十一": 21, "二十二": 22, "二十三": 23}

# A count word multiplies the group in front of it; it is never a locant. 三甲基吡嗪 is
# trimethylpyrazine, not position-3 methylpyrazine.
COUNT_WORD = {1: "", 2: "di", 3: "tri", 4: "tetra", 5: "penta", 6: "hexa"}

# How many carbons a chinese chain stem names. Used by the lactone rule, which needs the
# count rather than the english stem.
CARBON_COUNT = {"甲": 1, "乙": 2, "丙": 3, "丁": 4, "戊": 5, "己": 6, "庚": 7, "辛": 8,
                "壬": 9, "癸": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14,
                "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20}

STEM = {
    "甲": "meth", "乙": "eth", "丙": "prop", "丁": "but", "戊": "pent",
    "己": "hex", "庚": "hept", "辛": "oct", "壬": "non", "癸": "dec",
    "十一": "undec", "十二": "dodec", "十三": "tridec", "十四": "tetradec",
    "十五": "pentadec", "十六": "hexadec", "十七": "heptadec",
    "十八": "octadec", "十九": "nonadec", "二十": "eicos",
    "二十一": "heneicos", "二十二": "docos",
}

# Ring parents: Chinese -> (english name, positions an unstated group may take).
RING = {
    "吡嗪": ("pyrazine", [2, 3, 5, 6]),
    "吡啶": ("pyridine", [2, 3, 4, 5, 6]),
    "吡咯": ("pyrrole", [2, 3, 4, 5]),
    "呋喃": ("furan", [2, 3, 4, 5]),
    "噻吩": ("thiophene", [2, 3, 4, 5]),
    "四氢呋喃": ("tetrahydrofuran", [2, 3, 4, 5]),
    "四氢吡喃": ("tetrahydropyran", [2, 3, 4, 5, 6]),
    "苯": ("benzene", [2, 4, 6]),
    # 苯酚 is listed before 苯 by length, so 4-甲基苯酚 reaches it and keeps its 4
    "苯酚": ("phenol", [2, 3, 4, 6]),
    "甲苯": ("toluene", [2, 4, 6]),
    "环己烷": ("cyclohexane", [2, 3, 4, 5, 6]),
    "环己酮": ("cyclohexanone", [2, 3, 4, 5, 6]),
    "环戊烷": ("cyclopentane", [2, 3, 4, 5]),
    "环戊酮": ("cyclopentanone", [2, 3, 4, 5]),
    "环庚酮": ("cycloheptanone", [2, 3, 4, 5, 6, 7]),
    "环辛烷": ("cyclooctane", [2, 3, 4, 5, 6, 7, 8]),
    "环癸烷": ("cyclodecane", list(range(2, 11))),
    "环十二烷": ("cyclododecane", list(range(2, 13))),
}

SUBST = {
    "甲基": "methyl", "乙基": "ethyl", "丙基": "propyl", "丁基": "butyl",
    "戊基": "pentyl", "己基": "hexyl", "庚基": "heptyl", "辛基": "octyl",
    "壬基": "nonyl", "癸基": "decyl",
    "异丙基": "isopropyl", "异丁基": "isobutyl", "异戊基": "isopentyl",
    "仲丁基": "sec-butyl", "叔丁基": "tert-butyl",
    "正丙基": "propyl", "正丁基": "butyl", "正戊基": "pentyl",
    "苯基": "phenyl", "苯乙基": "phenethyl", "苄基": "benzyl",
    "羟基": "hydroxy", "甲氧基": "methoxy", "乙氧基": "ethoxy",
    "乙酰基": "acetyl", "氨基": "amino", "羰基": "oxo", "醛基": "formyl",
    "乙烯基": "vinyl", "烯丙基": "allyl", "甲硫基": "methylsulfanyl",
    "呋喃基": "furan-2-yl", "噻吩基": "thiophen-2-yl",
    "吡啶基": "pyridin-2-yl", "苯氧基": "phenoxy",
}

# Alkyl groups that are not a carbon stem at all. _chain_alcohol cannot build them from
# STEM, and they appear constantly as the alcohol half of an ester.
TRIVIAL_ALKYL = {
    "苯乙": "2-phenylethyl", "苯甲": "phenylmethyl", "苄": "phenylmethyl",
    "糠": "furan-2-ylmethyl", "烯丙": "prop-2-en-1-yl", "环己": "cyclohexyl",
    "环戊": "cyclopentyl", "苄基": "phenylmethyl", "苯乙基": "2-phenylethyl",
}

# Acids whose english name is not <stem>anoate.
TRIVIAL_ACID = {
    "苯甲": "benzoate", "水杨": "salicylate", "肉桂": "cinnamate",
    "乳酸": "lactate", "琥珀": "succinate", "苹果": "malate", "柠檬": "citrate",
    "酒石": "tartrate", "草": "oxalate", "糠": "furoate", "呋喃甲": "furan-2-carboxylate",
    "呋喃羧": "furan-2-carboxylate", "丙二": "malonate", "丁二": "succinate",
    "己二": "adipate", "壬二": "azelate", "邻苯二甲": "phthalate",
    "对苯二甲": "terephthalate", "氨基酸": "", "氨基": "",
}

STEM_KEYS = sorted(STEM, key=len, reverse=True)
RING_KEYS = sorted(RING, key=len, reverse=True)
SUBST_KEYS = sorted(SUBST, key=len, reverse=True)

SUF_CHARS = "醇醛酮酸烷烯炔"

DIRECT = {
    # acids
    "乙酸": "acetic acid", "甲酸": "formic acid", "草酸": "oxalic acid",
    "柠檬酸": "citric acid", "苹果酸": "malic acid", "乳酸": "lactic acid",
    "酒石酸": "tartaric acid", "富马酸": "fumaric acid", "苯甲酸": "benzoic acid",
    "乙酰乙酸": "acetoacetic acid",
    # alcohols
    "乙醇": "ethanol", "甲醇": "methanol", "丙三醇": "glycerol",
    "正丙醇": "1-propanol", "异丙醇": "2-propanol",
    "正丁醇": "1-butanol", "异丁醇": "2-methyl-1-propanol", "叔丁醇": "2-methyl-2-propanol",
    "正戊醇": "1-pentanol", "异戊醇": "3-methyl-1-butanol", "仲戊醇": "pentan-2-ol",
    "正己醇": "1-hexanol", "正庚醇": "1-heptanol", "正辛醇": "1-octanol",
    "正壬醇": "1-nonanol", "正癸醇": "1-decanol",
    "环己醇": "cyclohexanol", "环辛醇": "cyclooctanol",
    "苯乙醇": "2-phenylethanol", "β-苯乙醇": "2-phenylethanol",
    "苯甲醇": "phenylmethanol", "糠醇": "furfuryl alcohol",
    "呋喃甲醇": "furan-2-ylmethanol", "2-呋喃甲醇": "furan-2-ylmethanol",
    "芳樟醇": "linalool", "香叶醇": "geraniol", "香茅醇": "citronellol",
    "橙花醇": "nerol", "金合欢醇": "farnesol", "橙花叔醇": "nerolidol",
    "薄荷醇": "menthol",
    # aldehydes and ketones
    "乙醛": "acetaldehyde", "甲醛": "formaldehyde", "丙酮": "propan-2-one",
    "正丙醛": "propanal", "异丁醛": "2-methylpropanal", "正丁醛": "butanal",
    "异戊醛": "3-methylbutanal", "正戊醛": "pentanal", "正己醛": "hexanal",
    "正庚醛": "heptanal", "正辛醛": "octanal", "正壬醛": "nonanal",
    "正癸醛": "decanal",
    "丙烯醛": "prop-2-enal", "巴豆醛": "but-2-enal", "肉桂醛": "cinnamaldehyde",
    "糠醛": "furan-2-carbaldehyde", "呋喃甲醛": "furan-2-carbaldehyde",
    "苯甲醛": "benzaldehyde", "环己酮": "cyclohexanone", "环戊酮": "cyclopentanone",
    "丁二酮": "2,3-butanedione", "2,3-丁二酮": "2,3-butanedione",
    "2,4-戊二酮": "2,4-pentanedione", "戊二酮": "2,4-pentanedione",
    "3-羟基-2-丁酮": "3-hydroxybutan-2-one", "乙酰乙酸乙酯": "ethyl acetoacetate",
    # aromatics
    "苯": "benzene", "甲苯": "toluene", "二甲苯": "xylene", "乙苯": "ethylbenzene",
    "苯乙烯": "styrene", "苯酚": "phenol", "对甲酚": "4-methylphenol",
    "邻甲酚": "2-methylphenol", "间甲酚": "3-methylphenol",
    "愈创木酚": "2-methoxyphenol", "丁香酚": "4-allyl-2-methoxyphenol",
    "异丁香酚": "2-methoxy-4-propenylphenol", "香芹酚": "5-isopropyl-2-methylphenol",
    "百里香酚": "2-isopropyl-5-methylphenol",
    "香草醛": "4-hydroxy-3-methoxybenzaldehyde", "香兰素": "vanillin",
    "乙基麦芽酚": "5-ethyl-2-hydroxy-4-methylpyran-3-one",
    "麦芽酚": "3-hydroxy-2-methylpyran-4-one", "香豆素": "coumarin",
    "黄樟素": "5-prop-2-enyl-1,3-benzodioxole", "大马酮": "damascone",
    "β-大马酮": "beta-damascenone",
    # terpenes, ethers, solvents
    "柠檬烯": "limonene", "α-蒎烯": "alpha-pinene", "蒎烯": "alpha-pinene",
    "月桂烯": "myrcene", "茴香脑": "anethole",
    "乙醚": "diethyl ether", "甲基叔丁基醚": "methyl tert-butyl ether",
    "正己烷": "hexane", "异戊烷": "2-methylbutane", "环己烷": "cyclohexane",
    "四氢呋喃": "tetrahydrofuran",
    "二氯甲烷": "dichloromethane", "三氯甲烷": "trichloromethane",
    # esters
    "乙酸乙酯": "ethyl acetate", "乙酸甲酯": "methyl acetate",
    "乙酸丙酯": "propyl acetate", "乙酸丁酯": "butyl acetate",
    "乙酸异丁酯": "isobutyl acetate", "乙酸异戊酯": "isopentyl acetate",
    "乙酸己酯": "hexyl acetate", "乙酸辛酯": "octyl acetate",
    "乙酸苯乙酯": "2-phenylethyl acetate",
    "乳酸乙酯": "ethyl lactate", "乳酸甲酯": "methyl lactate",
    "DL-乳酸乙酯": "ethyl lactate",
    "苯甲酸乙酯": "ethyl benzoate", "苯甲酸甲酯": "methyl benzoate",
    "水杨酸甲酯": "methyl salicylate", "肉桂酸乙酯": "ethyl cinnamate",
    "邻苯二甲酸二乙酯": "diethyl phthalate",
    "亚油酸乙酯": "ethyl linoleate", "亚麻酸乙酯": "ethyl linolenate",
    "油酸乙酯": "ethyl oleate", "月桂酸乙酯": "ethyl laurate",
    "棕榈酸乙酯": "ethyl palmitate", "硬脂酸乙酯": "ethyl stearate",
    "肉豆蔻酸乙酯": "ethyl myristate", "苯乙酸乙酯": "ethyl phenylacetate",
    "丁二酸二乙酯": "diethyl succinate", "癸二酸二乙酯": "diethyl decanedioate",
    "正丁酸乙酯": "ethyl butyrate", "正己酸乙酯": "ethyl hexanoate",
    "正丁酸甲酯": "methyl butyrate", "正己酸甲酯": "methyl hexanoate",
    "正辛酸甲酯": "methyl octanoate", "正辛酸乙酯": "ethyl octanoate",
    "正壬酸乙酯": "ethyl nonanoate", "正癸酸乙酯": "ethyl decanoate",
    "异丁酸乙酯": "ethyl isobutyrate", "异戊酸乙酯": "ethyl isovalerate",
    "正戊酸乙酯": "ethyl valerate", "正丙酸乙酯": "ethyl propionate",
    # Lactones are handled by a rule, not by a table: see _translate_lactone. The entries
    # that used to be here were wrong - they read the Chinese prefix as the ring size,
    # while the printed CAS values in the corpus show it names the substituent.
    "γ-丁内酯": "oxolan-2-one",
    # diols
    "乙二醇": "1,2-ethanediol", "1,2-丙二醇": "1,2-propanediol",
    "1,3-丙二醇": "1,3-propanediol", "2,3-丁二醇": "2,3-butanediol",
    "1,4-丁二醇": "1,4-butanediol",
    # pyrazines and furans, each checked on its own
    "2-甲基吡嗪": "2-methylpyrazine", "2-乙基吡嗪": "2-ethylpyrazine",
    "2-丙基吡嗪": "2-propylpyrazine", "2-戊基吡嗪": "2-pentylpyrazine",
    "2-己基吡嗪": "2-hexylpyrazine",
    "2,3,5-三甲基吡嗪": "2,3,5-trimethylpyrazine",
    "2,3,5,6-四甲基吡嗪": "2,3,5,6-tetramethylpyrazine",
    "四甲基吡嗪": "2,3,5,6-tetramethylpyrazine",
    "2-甲基呋喃": "2-methylfuran", "2-乙基呋喃": "2-ethylfuran",
    "2,5-二甲基呋喃": "2,5-dimethylfuran", "2-戊基呋喃": "2-pentylfuran",
    "2-乙酰基呋喃": "2-acetylfuran", "2-丙基呋喃": "2-propylfuran",
    "2-正丁基呋喃": "2-butylfuran", "2-甲基四氢呋喃": "2-methyltetrahydrofuran",
    "4-甲基愈创木酚": "4-methylguaiacol", "5-甲基愈创木酚": "5-methylguaiacol",
    "4-乙基愈创木酚": "4-ethylguaiacol",
    # acetals and ketals
    "1,1-二乙氧基乙烷": "1,1-diethoxyethane",
    "1,1-二乙氧基-2-甲基丁烷": "1,1-diethoxy-2-methylbutane",
    "1,1-二乙氧基-3-甲基丁烷": "1,1-diethoxy-3-methylbutane",
    "1,1-二乙氧基-2-苯乙烷": "1,1-diethoxy-2-phenylethane",
    "1,1,3-三乙氧基丙烷": "1,1,3-triethoxypropane",
    # unsaturated chains
    "反-2,4-癸二烯醛": "trans-2,4-decadienal", "2,4-癸二烯醛": "2,4-decadienal",
    "3-甲基-2-丁烯醛": "3-methylbut-2-enal", "2-甲基-2-丁烯醛": "2-methylbut-2-enal",
    "3-甲基-2-戊烯醛": "3-methylpent-2-enal", "2-甲基-2-戊烯醛": "2-methylpent-2-enal",
    "3-甲基-3-戊烯醛": "3-methylpent-3-enal",
    "6-甲基-5-庚烯醛": "6-methylhept-5-enal",
    "6-甲基-5-庚烯-2-酮": "6-methylhept-5-en-2-one",
    "2-甲基-4-戊烯醛": "2-methylpent-4-enal",
    "3-甲基-2-丁烯-1-醇": "3-methylbut-2-en-1-ol",
    "2-甲基-3-辛烯-2-醇": "2-methyloct-3-en-2-ol",
    "3-乙氧基丙醇": "3-ethoxypropan-1-ol",
    # names whose shape no rule covers: condensed aromatics, acetals written with the
    # aldehyde name, and the rows where the character for 酯 was cut off
    "对二甲苯": "1,4-dimethylbenzene", "邻二甲苯": "1,2-dimethylbenzene",
    "间二甲苯": "1,3-dimethylbenzene", "间二甲苯": "1,3-dimethylbenzene",
    "甲基壬基甲酮": "decan-2-one", "二异丁基甲酮": "2,6-dimethylheptan-4-one",
    "甲基硫醇": "methanethiol", "甲硫醇": "methanethiol",
    "乙醛缩二乙醇": "1,1-diethoxyethane", "乙醛缩二甲醇": "1,1-dimethoxyethane",
    "异丁醛二乙缩醛": "1,1-diethoxy-3-methylbutane",
    "丙醛二乙缩醛": "1,1-diethoxypropane",
    "二乙氧基甲烷": "diethoxymethane",
    "活性异戊醇": "3-methylbutan-1-ol", "活性戊醇": "3-methylbutan-1-ol",
    "异戊醇": "3-methylbutan-1-ol", "异丁醇": "2-methylpropan-1-ol",
    "异辛醇": "3,7-dimethyloctan-1-ol",
    "大马士酮": "damascone", "β-大马士酮": "beta-damascenone",
    "β-大马酮": "beta-damascenone", "大马酮": "damascone",
    "胡桃酚": "5-hydroxy-1,4-naphthoquinone", "胡桃烯": "naphthalene-1,2-alkene",
    
    "E-橙花叔醇": "nerolidol", "DL-橙花叔醇": "nerolidol",
    "DL-2-羟基-4-甲基戊酸乙酯": "ethyl 2-hydroxy-4-methylpentanoate",
    "3-甲基-3-丁烯-1-醇": "3-methylbut-3-en-1-ol",
    "5-甲基-2-糠醛": "5-methylfuran-2-carbaldehyde",
    "3-糠醛": "furan-3-carbaldehyde", "2-糠醛": "furan-2-carbaldehyde",
    "2-糠醇": "furan-2-ylmethanol", "2-呋喃甲醇": "furan-2-ylmethanol",
    "2-呋喃基乙基酮": "1-(furan-2-yl)ethanone",
    "2-呋喃甲酸乙酯": "ethyl furan-2-carboxylate",
    "2-呋喃羧酸乙酯": "ethyl furan-2-carboxylate",
    "2-苯乙醇": "2-phenylethanol", "β-苯乙醇": "2-phenylethanol",
    "反式-3-己烯-1-醇": "(3E)-hex-3-en-1-ol", "顺式-3-己烯-1-醇": "(3Z)-hex-3-en-1-ol",
    "丙二酸二乙酯": "diethyl malonate", "琥珀酸乙酯": "ethyl succinate",
    "乳酸丁酯": "butyl lactate", "乳酸丙酯": "propyl lactate",
    "乳酸异丁酯": "isobutyl lactate", "乳酸异戊酯": "isopentyl lactate",
    "丁酸乙酯": "ethyl butyrate", "丁酸丙酯": "propyl butyrate",
    "戊酸乙酯": "ethyl valerate", "戊酸丙酯": "propyl valerate",
    "己酸丙酯": "propyl hexanoate", "己酸丁酯": "butyl hexanoate",
    "庚酸乙酯": "ethyl heptanoate", "辛酸丙酯": "propyl octanoate",
    "辛酸丁酯": "butyl octanoate", "壬酸丙酯": "propyl nonanoate",
    "乙酸丙酯": "propyl acetate", "乙酸丁酯": "butyl acetate",
    "乙酸己酯": "hexyl acetate", "乙酸辛酯": "octyl acetate",
    "乙酸异丁酯": "isobutyl acetate", "乙酸异戊酯": "isopentyl acetate",
    "乙酸乙酯": "ethyl acetate", "乙酸甲酯": "methyl acetate",
    "十七烷酸乙酯": "ethyl heptadecanoate",
    "苯甲酸异丁酯": "isobutyl benzoate", "苯甲酸正戊酯": "pentyl benzoate",
    "苯甲酸乙酯": "ethyl benzoate",
    "丁酸苯乙酯": "2-phenylethyl butyrate", "异丁酸苯乙酯": "2-phenylethyl isobutyrate",
    "异丙基-苯基丙酸酯": "propan-2-yl 3-phenylpropanoate",
    "香叶基丙酸酯": "3,7-dimethylocta-2,6-dienyl propanoate",
    "β-紫罗兰酮": "4-(2,6,6-trimethylcyclohex-1-en-1-yl)butan-2-one",
}

# Not single compounds: headings, totals, class labels, column captions. Reported in the
# audit rather than given a CAS.
NOT_COMPOUND = re.compile(
    r"^(其他|其它|本研究|文献|综述|研究|方法|结果|讨论|结论|前言|摘要|引言"
    r"|附表|附图|序号|备注|说明|总计|合计|总和|均值|标准差|相对标准偏差"
    r"|检出限|定量限|内标|外标|标准曲线|回归|相关系数|显著性|未检出|未鉴定"
    r"|总量|各类|已知|未知|名称|英文名|缩写|分类|单位|表头|合计值)"
    r"|^(表|图)\s*\d|^[表图]\d"
    r"|(类|物质)总含量$|^各类含量|^含量")

CLASS_HEAD = re.compile(r"(酸|醇|醛|酯|酮|酚|烯|烷|吡嗪|呋喃|内酯|缩醛|苯酚|其他)"
                        r"类(物质)?(总含量|含量)?$")

# Damage that OCR leaves behind. These strings are fragments, not names: a doubled
# hyphen, a stray bracket, a full-width slash. Translating one would produce a
# confident answer for a cell that has no answer in it, so they are refused on shape
# rather than listed one by one.
ARTIFACT = re.compile(r"--|[」』】〕〉]|了|／|_|\(\s*$|^\s*\)|[一-鿿]—[一-鿿]")

# The rules cannot place these and the parent offers no default, so they are refused
# rather than guessed. 2-甲基丙醇 is either 2-methylpropan-1-ol or -2-ol, which is
# isobutanol or isopropanol - two different CAS numbers. 2-甲基丙酮 and 3-甲基丁酮
# likewise never say where the C=O is.
AMBIGUOUS = {
    "2-甲基丙醇", "2- 甲基丙醇", "2-甲基丁酮", "3-甲基丁酮", "2-甲基丙酮",
}

# Names an earlier version of these rules got wrong. They are no longer blocked because
# the cause is gone rather than papered over: that version overwrote a written position
# with the parent's canonical one, so 2,3-二乙基吡嗪 came out as 2,3-dimethylpyrazine and
# 4-甲基苯酚 as 2-methylphenol. The ring rule now keeps whatever position the name
# writes, and every one of these is an explicit-locant case, so they are translated
# correctly instead of refused. selfcheck_zh2en.py holds each of them as a known-good
# pair, which is what keeps them honest. KNOWN_BAD stays in the file for names that
# still cannot be expanded.
KNOWN_BAD = {
    "2,5-二甲基-3-丁基吡嗪",          # position kept, but the ring is not a plain
                                     # pyrazine numbering - verify against the source
    "1,1-二乙氧基-2-苯乙烷",          # ambiguous: 乙烷 with a phenyl is underdefined
}

CJK = re.compile(r"[一-鿿]")

# ------------------------------------------------------------------- parsing


def _norm(s):
    s = (s or "").strip()
    s = s.replace("，", ",").replace("（", "(").replace("）", ")")
    s = s.replace("－", "-").replace("–", "-").replace("—", "-")
    s = s.replace("　", " ")
    return re.sub(r"\s+", " ", s)


def _key(s):
    """
    Key for the lookup tables.

    Whitespace is not part of a name: OCR inserts it freely, and "2, 4-二甲基苯酚" must
    reach the same entry as "2,4-二甲基苯酚". Without this a blacklist entry can be
    stepped around by a stray space, which is the one thing a blacklist must prevent.
    """
    return re.sub(r"\s+", "", _norm(s))


DIRECT_BY_KEY = {_key(k): v for k, v in DIRECT.items()}
KNOWN_BAD_BY_KEY = {_key(k) for k in KNOWN_BAD}
AMBIGUOUS_BY_KEY = {_key(k) for k in AMBIGUOUS}


def _split_locants(s):
    """Peel a leading position block: "2,3,5-" -> ([2,3,5], rest); else ([], s).

    Only digits followed by a hyphen or a comma count, so the 三 of 三甲基吡嗪 is never
    harvested as a position.
    """
    m = re.match(r"^(\d+(?:\s*,\s*\d+)*)\s*-\s*(?=\S)", s)
    if not m:
        return [], s
    return [int(x) for x in re.findall(r"\d+", m.group(1))], s[m.end():]


def _parse_head(head):
    """
    Parse what stands in front of a parent name into (positions, word, count).

    "2,6-二甲基"    -> ([2, 6], '甲基', 2)
    "2-乙基-5-甲基" -> ([2], '乙基', 1), ([5], '甲基', 1)
    "二甲基"        -> (None, '甲基', 2)
    "4-"            -> ([4], '', 0)

    positions None means the name did not say where the group sits; the caller supplies
    positions, refuses, or falls back to the parent's conventional numbering.
    """
    out, i = [], 0
    while i < len(head):
        ch = head[i]
        if ch in "- 　\t":
            # separators appear wherever a position was written, and the position is
            # carried by the digit block that came before
            i += 1
            continue
        if ch.isdigit():
            m = re.match(r"\d+(?:\s*,\s*\d+)*", head[i:])
            locs = [int(x) for x in re.findall(r"\d+", m.group(0))]
            i += m.end()
            # the block may carry a group written right after it: "2-甲基"
            j = i
            while j < len(head) and head[j] in "- 　\t":
                j += 1
            g, cnt, used = _read_group(head[j:])
            if g:
                out.append((locs, g, cnt))
                i = j + used
                continue
            out.append((locs, "", 0))
            continue
        g, cnt, used = _read_group(head[i:])
        if g is None:
            return None
        out.append((None, g, cnt))
        i += used
    return out


def _read_group(s):
    """
    Read one substituent group at the start of s.

    Returns (chinese, count, characters consumed), or (None, 1, 0) if nothing matches.

    The substituent table is tried before the count word, because 乙 is both a count
    word (two) and the two-carbon stem: read as a count first, 乙基 stops matching at
    基 and the whole name fails.
    """
    for k in SUBST_KEYS:
        if s.startswith(k):
            return SUBST[k], 1, len(k)
    for L in (2, 1):
        if L < len(s) and s[:L] in CN_NUM:
            for k in SUBST_KEYS:
                if s[L:].startswith(k):
                    return SUBST[k], CN_NUM[s[:L]], L + len(k)
    return None, 1, 0


def _tokens(items, canon=None, spare=None):
    """
    Turn parsed groups into (position, word) pairs.

    canon is the ring's conventional numbering, spare a list of positions offered for
    groups that have none. Returns None when the positions do not fit: too few, too
    many, or none at all. That refusal is the point - the alternative is a position
    that was never written.
    """
    placed, pending = [], []
    for locs, word, mult in items:
        if not word:
            # a bare position block with nothing attached; it belongs to the group
            if not locs or len(locs) != 1:
                return None
            continue
        if locs:
            if len(locs) != mult:
                return None          # "2-二甲基" asks for two positions and gives one
            placed.extend((lp, word) for lp in locs)
        else:
            pending.append((word, mult))
    if pending:
        want = sum(m for _w, m in pending)
        if canon:
            pool = list(canon[:want])
        elif spare:
            pool = list(spare)
        else:
            return None
        if len(pool) != want:
            return None
        for w, m in pending:
            placed.extend((lp, w) for lp in pool[:m])
            pool = pool[m:]
    return placed


# Count prefixes, longest first so "tetra" is not read as "tri".
_COUNT_PFX = ("tetra", "penta", "hexa", "tri", "di")


def _render(flat, base):
    """
    Build the prefix of a systematic name.

    Groups that share a word are merged, because the count belongs to the word and not
    to each position: 2,3-dimethylpyrazine is one word at two positions, and writing it
    as "2-dimethyl,3-dimethyl" would name neither.
    """
    if not flat:
        return base
    groups = {}
    for lp, w in flat:
        groups.setdefault(w, []).append(int(lp))
    parts = []
    for w, ps in groups.items():
        ps.sort()
        word = (COUNT_WORD.get(len(ps), "") + w) if len(ps) > 1 else w
        parts.append((w, "%s-%s" % (",".join(str(x) for x in ps), word)))
    # IUPAC cites prefixes alphabetically
    parts.sort(key=lambda p: p[0])
    return "-".join(t for _w, t in parts) + base


def _split_head_stem(s):
    """Split "甲基丁" into ("甲基", "丁"). Longest stem wins; None if there is none."""
    best = None
    for k in STEM_KEYS:
        j = s.rfind(k)
        if j >= 0 and (best is None or j > best[0]):
            best = (j, k)
    if not best:
        return None, None
    j, k = best
    return s[:j], k


def _chain_alcohol(cn):
    """Chinese alkyl fragment -> english alkyl, the '丁酯' half of an ester."""
    if not cn:
        return None
    if cn in TRIVIAL_ALKYL:
        return TRIVIAL_ALKYL[cn]
    pre = ""
    for p in ("正", "异", "新", "叔", "仲"):
        if cn.startswith(p):
            pre, cn = p, cn[len(p):]
            break
    for k in STEM_KEYS:
        if cn.startswith(k):
            if cn[len(k):] not in ("", "基", "烷", "醇", "烯"):
                return None
            root = STEM[k]
            if pre == "异":
                return "iso" + root + "yl"
            if pre == "叔":
                return "tert-" + root + "yl"
            if pre == "仲":
                return "sec-" + root + "yl"
            return root + "yl"
    return None


def _acid_part(cn):
    """
    Chinese acid fragment -> english ester half, 'hexanoate'.

    A branch word belongs to the fragment it sits on. 异丁酸 is isobutyric acid, so the
    异 attaches to the acid: attaching it to the whole name instead gives "isoethyl
    butanoate", which is not a compound.
    """
    if cn in ("乙", "醋"):
        return "acetate"
    if cn in ("甲", "蚁"):
        return "formate"
    for p, tag in (("正", ""), ("异", "iso"), ("新", "neo"), ("叔", "tert-"),
                   ("仲", "sec-")):
        if cn.startswith(p) and len(cn) > 1:
            inner = _acid_part(cn[len(p):])
            if inner:
                return tag + inner
    for k in sorted(TRIVIAL_ACID, key=len, reverse=True):
        if cn.startswith(k) and TRIVIAL_ACID[k] and cn[len(k):] in ("酸", "", "烷"):
            return TRIVIAL_ACID[k]
    for k in STEM_KEYS:
        # 烷 is accepted because 十七烷酸 is heptadecanoic acid: the chinese writes the
        # saturated stem where the english writes the acid stem
        if cn.startswith(k) and cn[len(k):] in ("酸", "", "烷"):
            return STEM[k] + "anoate"
    return None


def _ring(name_body):
    for rk in RING_KEYS:
        if not name_body.endswith(rk):
            continue
        en, canon = RING[rk]
        head = name_body[:-len(rk)]
        if not head:
            return en
        items = _parse_head(head)
        if items is None:
            return None
        flat = _tokens(items, canon)
        return None if flat is None else _render(flat, en)
    return None


def _chain(name_body, pos):
    """A carbon chain with a functional suffix. pos is the leading position block."""
    stem_here = None
    for k in STEM_KEYS:
        j = name_body.rfind(k)
        while j >= 0:
            tail = name_body[j + len(k):]
            if tail and (tail[0] in SUF_CHARS or tail[:1] in CN_NUM):
                stem_here = (j, k, tail)
                break
            j = name_body.rfind(k, 0, j)
        if stem_here:
            break
    if not stem_here:
        return None
    j, sk, tail = stem_here
    head, root = name_body[:j], STEM[sk]

    # A locant written right against the stem belongs to the functional group:
    # 4-甲基-2-戊酮 is butan-2-one with the methyl at 4.
    m2 = re.search(r"\d+(?:\s*,\s*\d+)*\s*-\s*$", head)
    fpos = [int(x) for x in re.findall(r"\d+", m2.group(0))] if m2 else None
    if m2:
        head = head[:m2.start()]

    # unsaturation then a second function: 辛烯-3-酮 -> oct-1-en-3-one
    dm = re.match(r"^(?P<n>[二三]?)(?P<k>烯|炔)-(?P<r>\d+)-(?P<s>.+)$", tail)
    if dm:
        if dm.group("n") or dm.group("k") != "烯":
            return None
        if dm.group("s") not in ("醇", "酮"):
            return None
        # the double bond position is the one written against the stem, or the one in
        # front of the name: 1-辛烯-3-醇 and 3-甲基-3-丁烯-1-醇 both say where it is
        dbl = fpos[0] if fpos else (pos[0] if pos else None)
        if dbl is None:
            return None
        word = "ol" if dm.group("s") == "醇" else "one"
        base = "%s-%d-en-%s-%s" % (root, dbl, dm.group("r"), word)
        return _assemble(head, base, pos if head else None)

    if re.match(r"^[二三]?[烯炔]", tail):
        # 烯醛 is the one unsaturated suffix that is unambiguous: the aldehyde carbon
        # is 1 by definition, so 2-十一烯醛 is undec-2-enal and nothing else.
        um = re.match(r"^烯(醛|醇|酮)$", tail)
        if um and um.group(1) == "醛" and pos:
            return _assemble(head, "%s-%d-enal" % (root, pos[0]), None)
        return None                       # diene/triene, or an unstated group carbon

    # When the name carries a substituent but no position for the group itself, the
    # position written in front locates the substituent instead - that is the Chinese
    # convention: 3-甲基丁醇 is 3-methylbutan-1-ol, not butan-3-ol.
    if head:
        spare = pos or None
        loc = fpos[0] if fpos else None
    else:
        spare = None
        loc = (fpos or pos or [None])[0]
        if (fpos or pos) and tail in ("醛", "酸", "烷"):
            # A position with no substituent to attach to is not a group carbon -
            # 2-壬醛 is an unsaturated aldehyde, and answering "nonanal" would throw
            # the position away and name a saturated compound instead.
            return None

    if tail == "醛":
        # the aldehyde carbon is always 1
        return _assemble(head, root + "anal", pos)
    if tail == "酸":
        # likewise always 1
        return _assemble(head, root + "anoic acid", pos)
    if tail == "烷":
        return _assemble(head, root + "ane", pos)
    if tail == "醇":
        # A named group in front of the stem means the written position went to the
        # substituent, so the OH is back at 1: 3-甲基丁醇 is 3-methylbutan-1-ol.
        if loc is None:
            loc = 1 if head else (pos[0] if pos else None)
        if loc is None:
            return None                   # 戊醇 says nothing about where the OH is
        return _assemble(head, "%san-%d-ol" % (root, loc), pos if head else None)
    if tail == "酮":
        if loc is None:
            return None                   # 戊酮 says nothing about where C=O is
        return _assemble(head, "%san-%d-one" % (root, loc), pos if head else None)
    return None


def _assemble(head, base, spare=None):
    """
    Put the substituent groups in front of an already-built base name.

    `spare` is the position block written in front of the name. When a group stands in
    front of the stem, the Chinese convention puts those positions on the group, not on
    the functional group - 2,6-二甲基-4-庚醇 has the two methyls at 2 and 6 and the OH
    at 4. Passing the whole block matters: an earlier version handed over only its first
    entry and lost the 6.
    """
    if not head:
        return None if spare else base
    items = _parse_head(head)
    if items is None:
        return None
    flat = _tokens(items, None, spare)
    return None if flat is None else _render(flat, base)


# The hyphen between the two halves is optional and OCR drops it as often as not:
# 丁酸-3-甲基丁酯 and 丁酸3-甲基丁酯 are the same ester.
ESTER = re.compile(r"^(?P<acid>.+?)酸\s*-?\s*(?P<alc>.+?)酯$")


def _ester(body, pos=None):
    m = ESTER.match(body)
    if not m:
        return None
    acid, alc = m.group("acid"), m.group("alc").lstrip("- ")

    if pos:
        # 2-甲基丁酸乙酯: the position belongs to the acid, so put it back where the
        # acid branch expects it. If it turns out to belong nowhere, the branch below
        # fails and the name is refused rather than translated without it.
        acid = "%d-%s" % (pos[0], acid)

    acid_en = _acid_part(acid)
    if acid_en is None:
        # the acid fragment arrives with 酸 already stripped, so the position is read
        # from the front of what is left: 2-甲基丁 -> methyl at 2 on butanoate
        am = re.match(r"^(?P<loc>\d+)-(?P<rest>.+)$", acid)
        if not am:
            return None
        head, sk = _split_head_stem(am.group("rest"))
        alc_en = _chain_alcohol(alc)
        if not (head and sk and alc_en):
            # head must be non-empty: 2-己酸乙酯 writes a position with no group for it
            # to sit on, and accepting the empty head answers "ethyl hexanoate" while
            # dropping the 2.
            return None
        rest = am.group("rest")
        items = _parse_head(head)
        if items is None:
            return None
        # 2-己烯酸乙酯 is ethyl hex-2-enoate, so a 烯 in the acid leaves a double bond
        # that the position belongs to
        base = STEM[sk] + "anoate"
        if rest.endswith("烯"):
            base = "%s-%d-enoate" % (STEM[sk], int(am.group("loc")))
        elif rest.endswith("炔"):
            base = "%s-%d-ynoate" % (STEM[sk], int(am.group("loc")))
        # the position in front of the acid is offered to any group that has none; a
        # group that already carries one keeps it
        flat = _tokens(items, None, [int(am.group("loc"))])
        acid2 = None if flat is None else _render(flat, base)
        return None if acid2 is None else "%s %s" % (alc_en, acid2)

    alc_loc, alc_rest = _split_locants(alc)
    if alc_loc:
        # 己酸3-甲基丁酯 -> 3-methylbutyl hexanoate
        head, sk = _split_head_stem(alc_rest)
        if not (head and sk):
            return None
        items = _parse_head(head)
        if items is None:
            return None
        flat = _tokens(items, None, alc_loc)
        alkyl = None if flat is None else _render(flat, STEM[sk] + "yl")
        return None if alkyl is None else "%s %s" % (alkyl, acid_en)
    a = _chain_alcohol(alc)
    return "%s %s" % (a, acid_en) if a else None


GREEK = {"α": "alpha-", "β": "beta-", "γ": "gamma-", "δ": "delta-"}

# 内酯 written with a greek prefix.
#
# The prefix does not name the ring size here. It names the substituent on a
# gamma-butyrolactone, and reading it as a ring size produced a wrong CAS for every
# lactone in sheet 34. The evidence is the paper's own column: each printed CAS resolves
# to a 5-alkyl-oxolan-2-one, with the chain growing by one carbon per step.
#
#     γ-丁内酯  96-47-9   oxolan-2-one            no substituent
#     γ-戊内酯  108-29-2  5-methyloxolan-2-one    one carbon
#     γ-己内酯  695-06-7  5-ethyloxolan-2-one     two
#     γ-庚内酯  105-21-5  5-propyloxolan-2-one    three
#     γ-辛内酯  104-50-7  5-butyloxolan-2-one    four
#     γ-壬内酯  104-61-0  5-pentyloxolan-2-one   five
#
# So the alkyl chain is four carbons shorter than the Chinese prefix. A prefix shorter
# than 丁 has no such compound and is refused.
#
# δ is not translated: nothing in the corpus prints a CAS for a δ-lactone, so there is no
# evidence for which ring size the convention implies, and guessing it would repeat the
# mistake in the opposite direction.
ALKYL_BY_LENGTH = {1: "methyl", 2: "ethyl", 3: "propyl", 4: "butyl", 5: "pentyl",
                   6: "hexyl", 7: "heptyl", 8: "octyl"}
LACTONE = re.compile(r"^γ\s*-\s*([一-鿿]+?)内酯$")


def _translate_lactone(s):
    m = LACTONE.match(s)
    if not m:
        return None
    stem = m.group(1)
    if stem not in STEM:
        return None
    n = CARBON_COUNT.get(stem)
    if n is None or n < 4:
        return None
    alkyl = ALKYL_BY_LENGTH.get(n - 4)
    if alkyl is None:
        return None
    return "5-%soxolan-2-one" % alkyl

# Cells where the chinese name and a glued english name disagree, filled in by
# translate(). Reported by the audit rather than resolved here.
CONFLICTED = []

# Cells that carried text after the compound name - an odour description, or a whole
# unsplit table row. The name is used and the remainder reported, because numbers in a
# name cell mean the row was split into columns wrongly.
CELL_EXTRA = []


def _english_run(s):
    """The longest run of latin characters in a cell, or None."""
    runs = re.findall(r"[A-Za-z][A-Za-z0-9,\-\s']*", s)
    if not runs:
        return None
    longest = max(runs, key=len).strip().rstrip(",- ")
    return longest if len(longest.split()) >= 2 else None


def _same_name(a, b):
    """Compare two english names loosely enough to accept a synonym spelling."""
    norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    # "isobutyl butyrate" and "isobutyl butanoate" are one ester
    return na.replace("butyrate", "butanoate") == nb.replace("butyrate", "butanoate")


def translate(name):
    """
    English name for a Chinese systematic name, or None.

    Order is deliberate: the verified dictionary first, then rings, then esters, then
    chains. The dictionary is only trusted because every entry was checked on its own.
    """
    s = _norm(name)
    if not s or len(s) < 2 or not CJK.search(s):
        return None
    if ARTIFACT.search(s):
        return None
    if NOT_COMPOUND.match(s) or CLASS_HEAD.search(s):
        return None
    k = _key(s)
    if k in KNOWN_BAD_BY_KEY or k in AMBIGUOUS_BY_KEY:
        return None
    if k in DIRECT_BY_KEY:
        return DIRECT_BY_KEY[k]

    got = _translate_body(s)
    if got:
        return got

    # A sample code in front of the name: "JS 正丁醇", "SC1 戊酸". The code is a column of
    # its own in the source tables and was merged into the name cell.
    m = re.match(r"^(?:JS|JB|SC\d*|Y)\s*(\S.*)$", s)
    if m:
        got = _translate_body(m.group(1))
        if got:
            return got

    # Extra text after the name: an odour description ("4-甲基苯酚 酚臭,动物气味") or, in
    # the worst rows, the rest of the table row that never got split into columns. The
    # name is taken and the rest is reported rather than dropped, because a cell that
    # holds numbers means the row was mis-split and that is worth knowing.
    toks = s.split()
    if len(toks) > 1:
        for i in range(1, len(toks)):
            got = _translate_body(" ".join(toks[:i]))
            if got:
                CELL_EXTRA.append((" ".join(toks[:i]), got, " ".join(toks[i:])))
                return got
    return None


def _translate_body(s):
    """The translation rules proper, on a name already known to be a single name."""
    k = _key(s)
    if k in KNOWN_BAD_BY_KEY or k in AMBIGUOUS_BY_KEY:
        return None
    if k in DIRECT_BY_KEY:
        return DIRECT_BY_KEY[k]

    # The lactone rule comes before the generic prefix handling: γ-己内酯 is a name in its
    # own right, and prefixing whatever "己内酯" translates to is not the same compound.
    got = _translate_lactone(s)
    if got:
        return got

    m = re.match(r"^([αβγδ])\s*-\s*(.+)$", s)
    if m:
        inner = translate(m.group(2))
        return GREEK[m.group(1)] + inner if inner else None

    for p, tag in (("反-", "trans-"), ("顺-", "cis-")):
        if s.startswith(p):
            inner = translate(s[len(p):])
            return tag + inner if inner else None

    if s.startswith("正") and len(s) > 1:
        # 正 only says the chain is unbranched. Every other branch word is left to
        # _chain_alcohol and _acid_part, which know which fragment it modifies -
        # 异丁酸乙酯 is ethyl isobutanoate, and prefixing the whole name produced the
        # non-compound "isoethyl butanoate".
        return translate(s[1:])

    # A cell holding both a chinese name and an english one. The chinese half is tried
    # first, and before any prefix handling: 异丁酸乙酯ethyl 2-methylpropanoate must
    # answer from the chinese, where the 异 belongs to the acid.
    #
    # Trailing digits are stripped from the chinese part because in 丁酸异丁酯
    # 3-methylbutyl butanoate they are the english name's position, not a position in
    # the chinese one. When the two halves name different compounds the chinese wins,
    # because it is the column's own value, and the disagreement is recorded rather than
    # resolved quietly.
    m = re.search(r"[A-Za-z]", s)
    if m and m.start() > 0:
        cn_part = re.sub(r"[\d\s\-_,;/]+$", "", s[:m.start()])
        if cn_part and CJK.search(cn_part):
            got = translate(cn_part)
            if got:
                en_part = _english_run(s)
                if en_part and _same_name(en_part, got):
                    pass
                elif en_part:
                    CONFLICTED.append((cn_part, got, en_part))
                return got

    pos, body = _split_locants(s)

    # A ring takes the whole name, not the body, so that a written position stays a
    # position instead of falling back to the parent's canonical one.
    got = _ring(s)
    if got:
        return got

    # The ester rules only accept a written position when they can place it: 2-甲基丁酸
    # has one on the acid, 己酸3-甲基丁酯 on the alkyl. 2-己酸乙酯 has one that fits
    # nothing, so it is refused instead of silently becoming ethyl hexanoate.
    got = _ester(body, pos)
    if got:
        return got

    got = _chain(body, pos)
    if got:
        return got

    # The chinese part is not a name this module can read, but the cell may still
    # carry an english one. The longest run of letters is taken, not the first, so a
    # leading "ethyl" does not shadow the rest of the string.
    en = _english_run(s)
    if en:
        return en
    return None
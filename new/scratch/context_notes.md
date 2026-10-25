# Context notes — 夏童 (25硕, supervisor 徐岩 / 马玥) research project

Source folder: `C:\Users\24252\Desktop\PPT\课题\26年\26年3月`
Files read: 4 target Office files (full text + embedded images inspected) + 2 Excel data files present in the same folder.
Temporary scripts/media: `C:\Users\24252\Desktop\PPT\课题\26年\26年3月\new\scratch\` (nothing else was created or modified).

---

## 1. `课题研究方案.docx` — research proposal (MOST IMPORTANT)

**Title:** 课题研究方案：基于机器学习的白酒香气感官评价与风味勾兑配比模型研究
(Machine-learning model for Baijiu aroma sensory evaluation and flavour-blending ratio)

**Overall purpose:** Use machine learning to build an empirical mapping F(X) = Y from volatile-compound concentrations (X) to aroma sensory-intensity indices (Y), so that physicochemical data can predict sensory evaluation, and finally derive a production-usable **《风味贡献权重表》(flavour contribution weight table)** for digital blending / product development. Cross-disciplinary collaboration with the "通用人工智能 & 食品生物健康交叉研究中心" (邓赵红; recommended 宁乔 = AI + chemoinformatics, 卞则康 = fuzzy computation for RATA/QDA subjectivity) and 孙晓燕 / 毛力 / 孙俊 teams.

**Key scientific problems:**
- Non-linear mapping between multi-component volatiles and complex sensory dimensions (traditional linear models fail on aroma superposition).
- Identifying inter-compound interactions: 协同 (synergy) / 拮抗 (antagonism) / 掩蔽 (masking) — via symbolic regression.
- Objectifying subjective sensory data (RATA / QDA) using fuzzy computation into interpretable machine weights.
- Collapsing the high-dimensional empirical formula into a **linear, production-applicable weight model via Taylor expansion** at a standard blending point.

**Thesis framework (6 chapters):**
1. 绪论 — background, current Baijiu blending technology, ML in food sensory science.
2. 数据采集与预处理 — sample collection + volatile determination (**GC-FID etc.**), sensory experiment design (**RATA index system**), normalisation/standardisation.
3. 关键风味化合物筛选 (based on **PLSR**) — sample-size control, **VIP value** analysis of compound contribution, factor mining and dimensionality reduction.
4. 香气预测模型构建 (based on **symbolic regression, SR**) — optimisation algorithms for formula derivation, F(X) establishment and validation, synergy/antagonism analysis.
5. 面向生产的线性塌缩模型与风味当量研究 — **Taylor expansion** approximation at the standard ratio point, generation and application of the 《风味贡献权重表》.
6. 结论与展望.

**Technical route — 4 layers:**
- **数据层:** collect **150 sample records**, containing **20 key compounds (X)** and **about 5–10 sensory intensity means (Y)**, then normalise.
- **筛选层:** **PLSR** first-round mining → **VIP** values → select significant compounds, and sets of compounds that influence each other or exist in ratio relationships.
- **建模层:** per Y index, **symbolic regression (SR)** to get scientifically interpretable empirical formulas capturing X–X interactions.
- **应用层:** **Taylor expansion** at the standard blending point → collapse to linear ratio model → output 《风味贡献权重表》 → link to blending and flavour-equivalent R&D.

**Deliverables (拟完成指标):** standardised preprocessing pipeline fusing 150 samples' physicochemical + sensory data; high-accuracy SR sensory prediction model identifying synergy/antagonism; a production guidance weight table keeping blending-ratio error within an acceptable range; cross-disciplinary output.

**"当前数据库处理目标" — current database analysis plan (explicit analysis tasks):**
1. **Global filtering + data mining:** among the already-screened **OAV > 1 compounds (20+ species)**, find the few compounds that have relationships, using **DBSCAN (density-based clustering)** or **Hierarchical Clustering**.
   - 1.1 **Variable-level hierarchical clustering** on the 20 compounds → lock onto the few compounds tightly clustered at the bottom of the dendrogram (e.g. A, C, D).
   - 1.2 **DBSCAN on samples** in the 3-D space of those variables → check whether all 150 records obey the pattern; identify the valid sample cluster so later modelling is accurate.
   - 1.3 **Local function mining:** apply **symbolic regression (SR)** to the selected "variable group" + "valid sample cluster".
2. **Alternative plan:** **correlation heat map + significance test** — Pearson R vs P-value on a **20×20 heat map = 400 correlation coefficients**, optimise the screen for high R with **P < 0.05**, look for compound clusters around the significant correlations, then model to determine possible ratio/function relationships.

**Embedded images:** 6 JPEGs — photographs of research-group poster boards (group members / team introductions). No technical-route figure.

**Mentioned:** 150 samples, 20 compounds, 5–10 Y indices, OAV > 1, 20×20 correlation heat map, P < 0.05, PLSR, VIP, SR, DBSCAN, hierarchical clustering, fuzzy computation, Taylor expansion, GC-FID, RATA, QDA.
**Not mentioned in this file:** GC-MS by name, 浓香型白酒 (it says 白酒 generically), 风味物质 threshold/阈值 values, Excel files, named brands.

---

## 2. `机器学习在白酒中的应用综述.docx` — literature review (DRAFT / INCOMPLETE)

**Title:** 机器学习在白酒中的应用 (Applications of machine learning in Baijiu)

**Overall purpose:** A short review being drafted by the student. It is an **unfinished draft** — only ~1.8 k characters; the abstract (摘要/Abstract) sections are empty headings, "2.白酒中机器学习" has no body text, and 1.2 决策树 is an empty heading. Only three references exist ([1] 周志华《机器学习》2016; [2] 2025白酒中期报告; [3] 中国酒业协会 2025中国白酒市场中期研究报告). No tables, no images.

**Content actually present:**
- 引言: AI/ML history (symbolic learning → statistical learning → deep learning); Baijiu as China's main distilled spirit, regional/craft-driven flavour diversity; market scale — **Q1 2025 CR6 (top-six) Baijiu brand revenue 1344.7 亿元**; the industry generates massive data, so AI-driven upgrading is unstoppable.
- 机器学习与模型: AI as a multi-field discipline (ML, NLP, computer vision, robotics); ML = non-explicit programming; Arthur Samuel's checkers program; ML cannot escape statistical probability and logic.
- **1.1 线性模型:** different datasets need different models ("货比三家"); methods named: **OLS 最小二乘法, PLS 偏最小二乘法, PCA 主成分分析**; linear models (线性回归, 对数几率回归, **LDA 信息判别分析**) are simple, easy to model, can weight multiple inputs, and can serve as the structural basis of higher-order models / be combined with other learners.
- **1.2 决策树:** heading only, no text.

**Relevance to the project:** shows the student's intended literature/theory base (linear models, PLS, PCA, LDA, decision trees) and gives the market-scale justification for the project. No data sources, datasets, Excel files, flavour compounds, 浓香型, GC-MS, OAV, 阈值, samples or brands are mentioned.

---

## 3. `26年研一下学期计划  夏童.docx` — semester plan (2nd semester, 2026)

**Title:** 26年研一下学期计划报告
**Direction:** 课题方向：使用机器学习对浓香型白酒的勾兑进行自动化升级
**Student:** 夏童, 25硕. **Supervisor:** 徐岩 教授. **Guidance group:** 马玥 助理研究员.

**Goal & content:** Through ML modelling, achieve **automatic prediction and optimisation of Baijiu blending ratios**; core goals: reduce manual intervention, guarantee product quality consistency, improve base-liquor (基酒) utilisation. Four stages: 数据采集与预处理 → 感官特征与风味化合物量化 → 机器学习模型构建与训练 → 模型应用与反馈优化.

**(1) 数据采集与预处理:**
- Widely collect **historical blending data**: records of the same formula blended at different ratios by blenders, plus the corresponding finished-product sensory evaluation data.
- Sensory evaluation relies on descriptor systems; explicitly defines: **焦香** (pyrazines, e.g. **2,6-二甲基吡嗪**, roasted); **甜香** (esters, e.g. **乙酸乙酯, 乳酸乙酯**, when above sensory threshold); **酸味** (short-chain organic acids: **乙酸, 乳酸**); **青草味** (**己醛**); **果香** (esters: **丁酸乙酯, 己酸乙酯**); **糟香** (phenols, e.g. **4-乙基愈创木酚**); **醇香** (higher alcohols, e.g. **异戊醇, 苯乙醇**). Standardised panel rating for consistency/repeatability; use **QDA or RATA** to determine the prominent flavour descriptors as ML input. Collect chemical analysis data of base/finished liquor: volatile flavour-compound concentrations via **HS-SPME (headspace solid-phase microextraction)** or **LLE (solvent extraction)**.
- **全国浓香型白酒定性定量数据整合 (national strong-aroma Baijiu qualitative/quantitative data integration)** — this is the core data task: collate all published literature with definite qualitative+quantitative data on 浓香型白酒 samples; record mainly compound concentrations; identify compounds by **CAS, RID, chemical formula**; look up **flavour-library thresholds**, compute **OAV**, and **require OAV > 1**; compile; **must label 产区 (region), 品牌 (brand), 酒厂 (distillery), 数据检测方式 (detection method)**. The resulting dataset is for ML pre-testing, aiming at empirical correlation between flavour descriptors and flavour quantitative data.

**(2) 感官特征与风味化合物量化:**
- Convert sensory descriptors into quantified features as ML input. **GC-MS or HPLC-MS** for qualitative/quantitative determination of volatile and non-volatile substances → build a comprehensive flavour-compound database. Then compute **OAV = concentration / sensory threshold**; **OAV > 1** means significant sensory contribution. Additionally use **AEDA dilution analysis (FD value)** to assess contribution to overall flavour. Synergy and masking effects can be determined as fuzzy ranges while tuning ML parameters. Determine, top-down and bottom-up, the number/names of compounds that can be entered into the database. Use changes in liquor-body detection data to determine the **non-linear relationship and parameters for a single flavour change**, representing specific weight relationships.

**(3) 机器学习模型构建与训练:**
- Supervised learning models on the quantified data: **线性模型、决策树、支持向量机、贝叶斯分类器、神经网络以及众多集成学习模型**, to predict flavour-compound contribution and the optimal blending ratio. First use an ML **soft-sensor (软测量) model** to relate compounds to typical flavour descriptors; synchronously analyse large amounts of varying data; select the data connected to a flavour descriptor; run empirical model tests — the final **projected parameters represent each compound's contribution value to a single typical descriptor**; then **reverse-validate** its effect by ratio-blending a model liquor. The model should ultimately auto-output blending ratios close to / coincident with the target flavour, reducing re-adjustment caused by base-liquor batch differences or plant condition changes.

**(4) 模型应用与反馈优化:**
- Evaluation metrics: **查准率、召回率、ROC、AUC、F1度量、代价曲线、交叉t检验、假设检验** to select the best model. Also **SHAP (Shapley Additive Explanations)** for interpretability — e.g. in 酱香型白酒 SHAP reveals the positive effect of **己酸乙酯** on 果香, or the dominant role of **乙酸** on 酸味.

**文献与技能学习:** 周志华《机器学习》 (linear models, decision trees, NN, SVM, Bayes, ensemble, semi-supervised); evaluation tools as above. **GC-MS**: prior learning via Teams videos/images. **QDA/RATA procedure**: select samples (both 基酒 and 成品酒); openly recruit **15–20 candidates**; sensory acuity + descriptive-ability tests; finally select **10 best assessors**; descriptor intensity scale calibration until all assessors converge on the same "10 point" intensity; randomise sample codes/order, rest between samples; enter all data via software, then **PCA** to form a sensory point map (感官点位图).

**学期计划 (semester plan — explicitly stated student tasks):**
1. **风味数据库数据差异统一化:** unify thresholds for compounds with **OAV close to 1** to guarantee consistent assessment; record 产区/品牌/possible process differences to classify the data; retain a small amount of inconsistent data to keep typical flavour substances complete. **Chinese-literature data entry and database submission.**
2. **小模型建立和数据处理方法学习尝试:** learn and apply basic analysis methods such as **SHAP and PLSR** to preprocess the existing data; try to find an ML model to construct and interpret the relationship for flavour contribution values; find similar models in open repositories, tune parameters and run them, preparing for blending experiments.
3. Summarise flavour experimental methods / research directions / status of 浓香型白酒 from the collected literature and draft a review; pre-draw the thesis framework and prepare the 绪论 (frontier, research status, experimental methods); design preparatory experiments.

**Embedded images:** 3 PNGs — screenshots of the student's PDF literature library (Zotero-style), listing ~18 English papers (e.g. "Characterization of the cellar mud…", "Volatilomics and Lipidomics reveal…", "8 Exploration of key aroma active co…", "10 Aroma characterization and reco…") plus a separate Chinese-thesis list of **~34 titles** (白酒风味轮及其评价方法…; 浓香型白酒勾兑调味的技术关键…; 基于OAV分析多粮浓香型调味酒陈酿过程中风味物质的变化; 基于GC-QTOF MS技术的浓香型白酒原酒质量评价技术研究; 基于关键风味组分分析不同质量等级浓香型白酒基酒; 机器学习在浓香型白酒智能酿造上的应用与展望 - 马毅; 基于电子舌/电子鼻/光谱的识别研究; 不同陈酿时间浓香型皖北名酒挥发性风味特征解析; 山东沂蒙老区浓香型白酒特征风味研究; 宜宾产区…; 洋河天之蓝 / 二锅头; 浓香型白酒的勾兑和调味浅析; etc.).
**Named samples/brands in text:** none by commercial brand (only style names 浓香型/酱香型 and generic 基酒/成品酒).

---

## 4. `学期计划汇报  夏童.pptx` — semester plan progress report (11 slides)

**Title (slide 1):** 2026年研一下学期计划 — 课题：机器学习结合进行浓香型白酒勾兑方案优化. 导师：徐岩；指导小组：马玥；汇报人：夏童；2025年3月9日 (date as written).

**Slide 2 — 目录:** 1.研究背景 2.研究目标 3.大论文框架及课题研究内容 4.本学期计划完成研究目标及其方案.

**Slide 3 — 研究背景 (白酒勾兑流程):** 原酒分级 → 入库贮存 → 酒体分析 (小样勾兑) → 配比勾兑. Blending mainly uses graded base liquors with different flavour bases, aged for different years (flavour compounds change), plus a small amount of 调味酒. Traditional blenders have problems: need long unified training, depend on the blender's own taste/smell acuity and master-apprentice transmission, and final flavour consistency — hence **high training cost, long time**. Try **AI blending** to: lower manual QC cost, provide possible new formulas, reduce manual intervention in intelligent production, reduce final quality fluctuation error.

**Slide 4 — 研究背景 (ML × Baijiu landscape):** stages 原料制曲 / 酿造发酵 / 成品分析 / 数据处理技术; current ML uses: raw-material (sorghum, wheat) quality grading (**决策融合算法**); 大曲 grading (**深度学习、卷积神经网络**); fermentation process monitoring (sensors + model output); flavour-substance monitoring (total acid / ester rapid detection); **基酒等级判别 (XGBoost, RFECA)**; authenticity discrimination (classification algorithms); **infrared-spectroscopy rapid detection**; **PCA, PLS and other data-processing methods**.

**Slide 5 — 课题内容及目标:** Goal = **build an ML model to assist in controlling the blending ratio**. Steps: 收集定性定量数据测试集 → 提取感官描述符作为属性词 → 品评确定感官数据 → 进行模型建立和验证过程.
- 课题拟解决的问题 (problems to solve):
  1. 不同品牌产区浓香型白酒的**定量差异与风味轮廓** (quantitative differences and flavour profiles of strong-aroma Baijiu from different brands/regions).
  2. 不同基酒配比产生的**风味差异向量化即风味权重** (vectorising the flavour differences produced by different base-liquor ratios, i.e. flavour weights).
  3. **权重配比与 OAV 配比的差异与贴合度，印证机器学习效力** (difference and fit between weight-based blending ratio and OAV-based blending ratio, to verify ML effectiveness).
- 课题创新点: 1. 定性定量数据与感官风味建立直接可视化的变化联系; 2. 机器学习模型与感官评价体系结合.
- *Note: the 4th 目录 item (this semester's plan) is covered on slides 9–11.*

**Slide 6 — 预拟课题框架与工作流程:** 主要章节 1. 浓香型白酒风味定性定量风味数据库 (collect published 浓香型 literature, summarise/analyse qualitative+quantitative data, build flavour profiles of the same/similar quality 浓香型 Baijiu); 2. 测定代表风味贡献的权重值 (**软测量** — use changes in liquor-body detection data to determine the non-linear relationship and parameters for a single flavour change, i.e. the weight); 3. 权重与风味评价体系结合验证模型效果 (blend using the weights, then sensory-compare against manually blended finished product of the same year/brand; feed the comparison back into parameter tuning to form a direct link between sensory and qualitative/quantitative data).

**Slide 7 — 风味轮廓与权重值测算:** Typical neural-network model (Input = 定性定量数据; Output = 感官数据, conventionally vectorised and set as standard values; Hidden layer; Value). Two optimisations: (1) **move part of the original Output forward to prevent overfitting**; (2) **secondary modelling of thresholds (阈值) and connection weights to obtain a link map between single compounds and sensory words** (感官词 A–G on the output side).

**Slide 8 — 计划前期/中后期工作流程:**
- Early: collect qualitative/quantitative flavour data → build database → determine the flavour profile of specific region/process/brand liquor data → separate sensory tests for sensory profiles → ML builds the change relationships and parameters → parameters form calculation formulas and weight values → **prepare a simulated liquor (模拟酒) according to the weight values for validation**.
- Mid-late (if validation results are good): select base liquors of different years/vintages and different flavour bases from distilleries and quantify them → input to model training to obtain weight parameters/formulas → blend according to weights → sensory testing to verify the blending effect.

**Slide 9 — 本学期计划完成研究目标:** 1. 精读文章 — ~**150 Chinese + English papers in total, ~90 Chinese and ~60 English**, covering 浓香型 flavour/sensory directions and Baijiu ML directions; 预计 3–5月. 2. 风味数据库建立 — build a physicochemical database of commercial finished 浓香型 Baijiu, mainly from published literature; 预计本月中旬. Plus sensory testing of different brands of finished liquor with a mature descriptor system + intensity calibration (4–5月). 3. 机器学习建立神经网络小模型 — find usable models in ML model libraries, tune, integrate parameters and calculation formulas (5–6月). 文案工作: start writing the review combining ML and 浓香型 Baijiu research status; draft thesis framework, 前言/研究现状/背景/创新点 (3–4月).

**Slide 10 — 本月目标：风味数据库建立:**
- Organise/statistic by **flavour-compound class, CAS number, compound structure**; enter data. Mark and divide by **工艺 (process), 产区 (region), 检测方法 (detection method)**; unify/uniformise the data.
- 一：**WOS literature search** — searched **300+ papers** with themes *strong flavor, aroma, luzhou baijiu*; screened to **20+ papers**, each providing **2–10 different 浓香型 quantitative datasets**.
- 二：中文文献搜集 (Chinese literature collection).
- 三：数据库建立 — 已录入 **近30篇 (nearly 30), including 基酒 and 成品酒**; 未录入 → 提交.
- Images: screenshots of the student's reference-manager library (English papers, e.g. "3 综述 Uncover the flavor code of strong-aroma baijiu…", "3 基酒 Analysis of aroma compounds in different grades of Luzhou Laojiao", "2 Volatilomics and Lipidomics revealed flavoring mechanism in baijiu", "5 Key Aroma Compounds and Aroma Characteristics in…", "8 Exploration of key aroma active compounds in strong flavor Baijiu during…", "10 Aroma characterization and reconstitution of strong-aroma baijiu Insights…", "DMU-SPME variable temperature extraction…", "Characterization of the cellar mud odor compounds…", "Influences of Non-Volatile Components on the Aroma of Strong-Aroma Baijiu", …) and a screenshot of the **actual working Excel sheet** with columns Order ID | CAS | Odorants | 中文名称 | SMILES | Threshold | Concentration (μg/L) | 1 LZ–2016 base SAB | 1 GJ–1573 | 2 Y1 μg/ml | 2 Y3 | 2 Y5 | 2 Y8 | 2 Y11 | 3 LZLJ-M7 | 3 LZLJ-T7 | 4 LS OAV | 5 S1/S2(F3)/S3/F1/F3 | 6 JH1/JH2/SC1–SC6 | 7 … | 9 B1-H/B1-L/B3-H/B3-L/B2-H/B2-L.

**Slide 11 — 3–6月目标：结合风味轮廓选取模型库进行训练:**
- 一：数据库白酒性质确定 — determine 产区/品牌/制作工艺 of the 浓香型 Baijiu in the database; **purchase the corresponding commercial finished Baijiu for sensory testing such as QDA to get sensory data**.
- 二：数据处理与分析 — carry out **data preprocessing and detailed analysis, e.g. PCA 主成分分析, and produce a flavour wheel (风味轮)**, to serve as ML input data.
- 三：模型选取 — because the relationship between sensory evaluation and qualitative/quantitative data is **non-linear and complex**, prioritise **neural networks**; put the data into the observation space, use simulation to observe goodness of fit, use AI to help write screening code and train.
- 四：调参库 **PyTorch** installation, learning and debugging.
- Image on this slide: a **QDA radar/spider flavour wheel** (axes: 酱香, 曲香, 粮香, 烘焙香, 花香, 水果香, 甜香, 陈香, 空杯香, 盐菜味, 酸味; 0–5 scale; three series RH-2 / RH-1 / RH-Y and XS-2 / XS-1 / XS-Y, captioned 图2 不同等级酱香产品特征风味定量分析) — i.e. the student is using this published radar-chart format as the template for the sensory (Y) data representation.

---

## 5. Bonus context — the two Excel data files in the same folder (NOT requested, but directly relevant)

### `data.xlsx` — the main working database (35 sheets, ~309 KB)
- Sheet 1 `all data`: **96 rows × 52 columns**. Core columns: **Order ID | CAS | Odorants | 中文名称 | SMILES | Threshold | Concentration (μg/L)** followed by per-study sample columns. Header groups present: `1 LZ–2016 base SAB (μg/L)`, `1 GJ–1573`, `2 Y1/Y3/Y5/Y8/Y11 (μg/ml or μg/L)`, `3 LZLJ-M7`, `3 LZLJ-T7`, `4 LS OAV`, `4 FS OAV`, `5 S1/S2(F3)/S3/F1/F3 (mg/L)`, `6 JH1/JH2/SC1…SC6 OAV`, `7 OAV Sample 1–3`, `9 B1-H/B1-L/B3-H/B3-L/B2-H/B2-L`, and more in `data总库`. Typical dominant compound: **己酸乙酯 (Ethyl Hexanoate, CAS 123-66-0)** with values in the 10⁵–10⁶ μg/L range; other frequent compounds: 异戊酸乙酯 (108-64-5), 丁酸乙酯 (105-54-4), 戊酸乙酯, 乙酸乙酯, 乳酸乙酯, 己酸, 乙酸, 苯乙醇, 愈创木酚类.
- Sheets 2–34 are **one sheet per source paper**, mostly with the same 3-block layout (raw data | cleaned block | 标准顺序 block), e.g.:
  - `2 Characterization of key odor…` — Compounds | threshold | LZ–2016 base SAB (Mean±SD) | GJ–1573 (Mean±SD) | OAV for both (50 compounds).
  - `5 Key Aroma Compounds and Arom…` — no. | flavor components | CAS | **Y1, Y3, Y5, Y8, Y11** | Threshold | OAV (132 rows).
  - `2 Decoding the Molecular Mecha…` — Threshold | Concentration LZLJ-M7 / LZLJ-T7 | OAV.
  - `5 Impact of Pulsed Electric Fi…` — Compound | Blank | S1 | S2(F3) | S3 | F1 | F3 (mg/L), 102 rows.
  - `8 Flavoromic Exploration of Reg…` — ID | compound | odor threshold | JH1 JH2 SC1–SC6 (34 rows).
  - `3 Unraveling variation on the…` — No | Category | Compounds | CAS | BC/SG | GJG | LZ (mg/L).
  - `11不同等级浓香型白酒基酒挥发性风味物质差异分析` — 序号 | 化合物 | 阈值/(mg·L⁻¹) | **OAV (优级/一级/二级/丢糟)** | 气味描述 | 浓度 | — note: contains `#VALUE!` errors and "NF" entries.
  - `13 四川不同产区…` — 序号 | 化合物 | 含量 A/B/C | 香味特征 | 阈值 | OAV A/B/C.
  - `16 5种品牌浓香型白酒香气成分分析`, `14基于GC×GC-MS…`, `15 基于全二维气相色谱-飞行时间质谱…`, `18 不同贮存年份的五粮浓香型白酒…`, `19 浓香、酱香、清香型…`, `20 三种香型白酒的ICP-OES…`, `21 基于GC-MS的浓香型白酒等级评判模型研究`, `25 山东沂蒙老区…`, `30 洋河绵柔型白酒关键风味成分`, `33 宜宾产区浓香型白酒风味特征及香气活性物质` (119 rows × 59 cols, sample codes S-Y1-H…S-Y6-H, S-L1-H, A-GJG-H, G-J1-H, J-Y1-H, plus matching "-L" blocks).
- **Named samples/brands found in the data:** LZ–2016 base SAB, **GJ–1573 (国窖1573)**, **LZLJ-M7 / LZLJ-T7 (泸州老窖)**, Y1/Y3/Y5/Y8/Y11 series, S1/S2(F3)/S3/F1/F3, JH1/JH2, SC1–SC6, B1-H/L, B2-H/L, B3-H/L, B4-H/L, B5-H/L, JSY, **JNC (剑南春)**, **WLY (五粮液)**, GJG, LGTQ, JPLG, GRD-1/2, GRD-JC, GRD-PD, 沂蒙老区 (Yimeng) samples, 优秀/一级/二级/丢糟 grade labels, S-Y* (宜宾) samples.

### `data总库.xlsx` — partial consolidated copy (13 sheets, ~143 KB)
- Sheet `all data`: **66 rows × 187 columns** — same schema as above but far wider (more sample columns) and fewer rows (66 vs 96). Values are numbers only (no "±SD" strings) — i.e. a **flattened numeric matrix for modelling**.
- Only ~11 of the 34 source-paper sheets are carried over; the other **23 source sheets (mostly the Chinese-named literature sheets) exist ONLY in `data.xlsx`** (differences: `11不同等级…`, `12 高粱营养品质…`, `13 四川不同产区…`, `14基于GC×GC-MS…`, `15 基于全二维…`, `16 5种品牌…`, `18 不同贮存年份…`, `19 浓香、酱香、清香…`, `20 三种香型白酒的ICP-OES…`, `21 基于GC-MS的浓香型白酒等级评判模型研究`, `22 浓香型白酒及其风味成分对乙醇代谢…`, `23 3个年份浓香型白酒香气成分比较研究`, `25 山东沂蒙老区…`, `26 浓香型白酒基酒挥发性成分分析及等级识别研究`, `27 基于GC-QTOF MS技术的…`, `28 酱香型和浓香型白酒中香气物质及其差异研究`, `29 应用GC-MS对两种原粮酿造的浓香型…`, `30 洋河绵柔型白酒关键风味成分`, `31 浓香型洋河天之蓝和清香型二锅头…`, `32 浓香型白酒基酒味觉特征与挥发性风味成分相关性研究`, `33 宜宾产区…`, plus three unnamed Chinese sheets). `data总库.xlsx` has one empty `Sheet9`.
- **Practical implication:** `data.xlsx` is the master/most complete; `data总库.xlsx` looks like an earlier or in-progress flattening for modelling and is currently **out of sync** with the master.

---

## 研究背景与数据分析需求（synthesis, Chinese, ≤300 words）

夏童（25硕，导师徐岩、指导马玥）的课题是**用机器学习把浓香型白酒勾兑从经验操作升级为数据驱动**：以挥发性化合物定性定量数据为 X，感官描述符强度（QDA/RATA 品评、风味轮）为 Y，建立可解释模型，输出生产用**《风味贡献权重表》**，用于预测并优化勾兑配比。

数据来自文献整合的浓香型白酒定性定量数据（检索 300 余篇筛出 20 余篇，中文近 30 篇，目标约 150 条样本），按 CAS、SMILES、产区、品牌、检测方法标记。分析链：**阈值→OAV（保留 OAV>1）→PLSR/VIP 筛选 20 种关键化合物→DBSCAN/层次聚类定位变量组与有效样本簇→符号回归建立 F(X)=Y→泰勒展开线性塌缩→权重表**；备选为 **20×20 相关性热图（R 与 P<0.05）**。

最有用的结果：(1) 清洗数据库，统一阈值与单位，给出 OAV>1 化合物清单及产区/品牌标签；(2) 相关性热图与显著性、层次聚类树状图、DBSCAN 样本簇图；(3) PLSR 的 VIP 排名与载荷图；(4) 各感官描述符的化合物贡献权重表/热图；(5) 权重配比与 OAV 配比的贴合度对比及模型验证指标。

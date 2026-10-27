import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const input = process.argv[2];
const outputDir = process.argv[3];
if (!input || !outputDir) throw new Error("Usage: node build_workbook.mjs design.json output-directory");
const d = JSON.parse(await fs.readFile(input, "utf8"));
await fs.mkdir(outputDir, {recursive:true});
const wb = Workbook.create();
const names = ["方案总览","350配方","浓度矩阵","浓度设置","配对统计","原始浓度"];
const s = Object.fromEntries(names.map(n=>[n,wb.worksheets.add(n)]));
const vars = d.compounds.filter(c=>!c.base);
const bases = d.compounds.filter(c=>c.base);
const byId = new Map(d.compounds.map((c,i)=>[c.id,{...c,row:i+6}]));
const col=n=>{let a="";for(;n;n=Math.floor((n-1)/26))a=String.fromCharCode(65+(n-1)%26)+a;return a;};
const write=(sh,row,values)=>sh.getRangeByIndexes(row-1,0,values.length,values[0].length).values=values;
const form=(sh,row,column,values)=>sh.getRangeByIndexes(row-1,column-1,values.length,values[0].length).formulas=values;
const title=(sh,text,note)=>{
  sh.getRange("A2").values=[[text]];
  sh.getRange("A2").format.font={name:"Arial",size:15,bold:true,color:"#17324D"};
  sh.getRange("A3").values=[[note]];
  sh.getRange("A3").format.font={name:"Arial",size:10,color:"#526274"};
};
const table=(sh,end,columns,width=16)=>{
  const last=col(columns);
  sh.showGridLines=false;
  sh.getRange("A5:"+last+end).format.font={name:"Arial",size:10,color:"#1F2937"};
  sh.getRange("A5:"+last+end).format.rowHeight=24;
  sh.getRange("A5:"+last+end).format.columnWidth=width;
  sh.getRange("A5:"+last+"5").format={
    fill:"#17324D",font:{name:"Arial",size:10,bold:true,color:"#FFFFFF"},
    horizontalAlignment:"center",verticalAlignment:"center",wrapText:true,rowHeight:44
  };
  sh.freezePanes.freezeRows(5);
  sh.freezePanes.freezeColumns(1);
  sh.tables.add("A5:"+last+end,true,"Table_"+names.indexOf(sh.name));
};

// Raw numeric observations, not the published or rounded OAV columns.
title(s["原始浓度"],"可用原始浓度 / Source concentrations","Source: all-data/可用化合物原始数据.xlsx; all data; 113 concentration columns; unit ug/L.");
write(s["原始浓度"],5,[["ID","中文名称","English name","CAS","阈值 ug/L",...d.raw_headers]]);
write(s["原始浓度"],6,d.compounds.map(c=>[c.id,c.name,c.english,c.cas,c.threshold,...c.raw]));
table(s["原始浓度"],46,118,16);
s["原始浓度"].getRange("B6:C46").format.columnWidth=35;
s["原始浓度"].getRange("E6:DN46").setNumberFormat("0.0000");
s["原始浓度"].getRange("A49").values=[["Git blob SHA: "+d.config.source_git_blob_sha]];
s["原始浓度"].getRange("A50").values=[["Missing values remain blank; true numeric zero is retained."]];
s["原始浓度"].getRange("A51").values=[["Method: https://www.itl.nist.gov/div898/handbook/pri/section5/pri521.htm"]];
s["原始浓度"].getRange("A52").values=[["I criterion: https://www.jmp.com/support/help/en/19.0/jmp/optimality-criteria.shtml"]];

// Statistics and the actual concentration levels own these calculations.
title(s["浓度设置"],"浓度范围与共同基底 / Concentration levels","Three levels: observed positive minimum / geometric midpoint / maximum. Two levels: median / maximum.");
write(s["浓度设置"],5,[["ID","中文名称","English name","CAS","角色 Role","档数","有效 n","原始最小","最小正值","原中位值","最大值","算术均值","阈值 ug/L","中位 OAV","均值 OAV","L ug/L","M ug/L","H ug/L","基底 ug/L","基底量 ug/瓶","浓度说明"]]);
write(s["浓度设置"],6,d.compounds.map(c=>[c.id,c.name,c.english,c.cas,c.base?"固定基底":"可变",c.nlevels,...Array(14).fill(null),
  c.base?"所有350瓶固定为均值":c.nlevels===3?"M为几何中点，区别于原中位值":"M为原中位值，H为最大值"]));
for(let i=0;i<d.compounds.length;i++){
  const r=i+6;
  form(s["浓度设置"],r,7,[[
    "=COUNT('原始浓度'!F"+r+":DN"+r+")",
    "=MIN('原始浓度'!F"+r+":DN"+r+")",
    "=_xlfn.MINIFS('原始浓度'!F"+r+":DN"+r+",'原始浓度'!F"+r+":DN"+r+',">0")',
    "=MEDIAN('原始浓度'!F"+r+":DN"+r+")",
    "=MAX('原始浓度'!F"+r+":DN"+r+")",
    "=AVERAGE('原始浓度'!F"+r+":DN"+r+")",
    "='原始浓度'!E"+r, "=J"+r+"/M"+r, "=L"+r+"/M"+r,
    '=IF(AND(E'+r+'="可变",F'+r+'=3),I'+r+',"")',
    '=IF(E'+r+'="固定基底","",IF(F'+r+'=3,SQRT(I'+r+'*K'+r+'),J'+r+'))',
    '=IF(E'+r+'="固定基底","",K'+r+')',
    '=IF(E'+r+'="固定基底",L'+r+',0)',
    "=S"+r+"*'方案总览'!$B$5/1000"
  ]]);
}
table(s["浓度设置"],46,21);
s["浓度设置"].getRange("B6:C46").format.columnWidth=35;
s["浓度设置"].getRange("H6:T46").setNumberFormat("0.0000");
s["浓度设置"].getRange("P6:R46").format.fill="#FFF5D9";
s["浓度设置"].getRange("U6:U46").format.columnWidth=43;

// Preparation list: IDs, level codes and four concentration/mass columns.
title(s["350配方"],"350次配制 / Preparation list","All samples contain the same 11-component background. T=train; R=independent preparation repeat; V=held-out validation.");
const rh=["样本编号","用途 Purpose","组成组","重复来源",
  "物质1","物质2","物质3","物质4","档1","档2","档3","档4",
  "浓度1 ug/L","浓度2 ug/L","浓度3 ug/L","浓度4 ug/L",
  "OAV1","OAV2","OAV3","OAV4","量1 ug/瓶","量2 ug/瓶","量3 ug/瓶","量4 ug/瓶",
  "ID1","ID2","ID3","ID4","可变物质数","体积 mL"];
write(s["350配方"],5,[rh]);
write(s["350配方"],6,d.rows.map(r=>[
  r.sample_id,r.purpose,r.composition_id,r.repeat_of,
  ...Array.from({length:4},(_,j)=>r.names[j]??""),
  ...Array.from({length:4},(_,j)=>r.codes[j]??""),
  ...Array(12).fill(null),...Array.from({length:4},(_,j)=>r.compound_ids[j]??""),
  r.compound_ids.length,null
]));
const cr=[],or=[],mr=[];
for(let i=0;i<350;i++){
  const r=i+6;
  const conc=[],oav=[],mass=[];
  for(let j=0;j<4;j++){
    const idc=col(25+j),code=col(9+j),cc=col(13+j);
    conc.push('=IF('+idc+r+'="","",INDEX(\'浓度设置\'!$P$6:$R$46,MATCH('+idc+r+',\'浓度设置\'!$A$6:$A$46,0),IF('+code+r+'="L",1,IF('+code+r+'="M",2,3))))');
    oav.push('=IF('+idc+r+'="","",'+cc+r+'/INDEX(\'浓度设置\'!$M$6:$M$46,MATCH('+idc+r+',\'浓度设置\'!$A$6:$A$46,0)))');
    mass.push('=IF('+idc+r+'="","",'+cc+r+'*$AD'+r+'/1000)');
  }
  cr.push(conc);or.push(oav);mr.push(mass);
}
form(s["350配方"],6,13,cr);
form(s["350配方"],6,17,or);
form(s["350配方"],6,21,mr);
form(s["350配方"],6,30,Array.from({length:350},()=>["='方案总览'!$B$5"]));
table(s["350配方"],355,30);
s["350配方"].getRange("E6:H355").format.columnWidth=28;
s["350配方"].getRange("M6:X355").setNumberFormat("0.0000");

// Flat concentration matrix for analysis and coverage calculations.
title(s["浓度矩阵"],"全部组分浓度 / Full concentration matrix","One row per planned preparation; zero=not added as a variable; fixed-background columns remain present.");
const ordered=[...vars,...bases];
write(s["浓度矩阵"],5,[["样本编号","用途 Purpose","拟合标记","可变数",...ordered.map(c=>c.id+" "+c.name+" (ug/L)")]]);
const mx=d.rows.map((r,i)=>{
  const er=i+6;
  return ["='350配方'!A"+er,"='350配方'!B"+er,'=IF(B'+er+'="拟合",1,0)',"='350配方'!AC"+er,
    ...vars.map(c=>"=SUMIFS('350配方'!$M"+er+":$P"+er+",'350配方'!$Y"+er+":$AB"+er+","+c.id+")"),
    ...bases.map(c=>"='浓度设置'!S"+byId.get(c.id).row)];
});
form(s["浓度矩阵"],6,1,mx);
table(s["浓度矩阵"],355,45,19);
s["浓度矩阵"].getRange("E6:AS355").setNumberFormat("0.0000");

// Pair statistics are calculation outputs, not model-effect estimates.
title(s["配对统计"],"435个配对的覆盖 / Pair coverage","Counts describe co-varying compounds, not demonstrated sensory interactions. Level-cell counts are a snapshot of this algorithm run.");
write(s["配对统计"],5,[["ID A","ID B","物质 A","物质 B","档位类型","拟合出现次数","重复出现次数","验证出现次数","不同背景数","已覆盖档位格","全部档位格","档位格比例"]]);
write(s["配对统计"],6,d.pairs.map(p=>[p.id_a,p.id_b,p.name_a,p.name_b,p.type,null,null,null,p.distinct_backgrounds,p.level_cells,p.possible_level_cells,null]));
for(let i=0;i<435;i++){
  const p=d.pairs[i], r=i+6,a=col(5+p.i),b=col(5+p.j);
  form(s["配对统计"],r,6,[["=COUNTIFS('浓度矩阵'!$C$6:$C$355,1,'浓度矩阵'!$"+a+"$6:$"+a+'$355,">0",\'浓度矩阵\'!$'+b+"$6:$"+b+'$355,">0")',
    '=COUNTIFS(\'浓度矩阵\'!$B$6:$B$355,"独立配制重复",\'浓度矩阵\'!$'+a+"$6:$"+a+'$355,">0",\'浓度矩阵\'!$'+b+"$6:$"+b+'$355,">0")',
    '=COUNTIFS(\'浓度矩阵\'!$B$6:$B$355,"留出验证",\'浓度矩阵\'!$'+a+"$6:$"+a+'$355,">0",\'浓度矩阵\'!$'+b+"$6:$"+b+'$355,">0")']]);
  form(s["配对统计"],r,12,[["=J"+r+"/K"+r]]);
}
table(s["配对统计"],440,12,17);
s["配对统计"].getRange("C6:D440").format.columnWidth=30;
s["配对统计"].getRange("L6:L440").setNumberFormat("0.0%");

const sh=s["方案总览"];
sh.showGridLines=false;sh.tabColor="#17324D";
title(sh,"组合覆盖与浓度选点 / Algorithm design","Design draft dated 2026-10-27. No sensory responses have been measured or simulated.");
sh.getRange("A5:B6").values=[["每瓶体积 mL",20],["乙醇 % v/v",53]];
sh.getRange("B5:B6").format.fill="#FFF5D9";
const metrics=[
  ["总配制次数","=COUNTA('350配方'!A6:A355)"],
  ["拟合配方",'=COUNTIFS(\'350配方\'!B6:B355,"拟合")'],
  ["独立配制重复",'=COUNTIFS(\'350配方\'!B6:B355,"独立配制重复")'],
  ["留出验证",'=COUNTIFS(\'350配方\'!B6:B355,"留出验证")'],
  ["可变化合物",30],["共同基底",11],
  ["配对总数",435],["拟合已覆盖配对",'=COUNTIFS(\'配对统计\'!F6:F440,">0")'],
  ["配对出现覆盖率","=B15/B14"],
  ["每对最少出现","=MIN('配对统计'!F6:F440)"],
  ["每对最多出现","=MAX('配对统计'!F6:F440)"],
  ["已覆盖浓度档位格","=SUM('配对统计'!J6:J440)"],
  ["全部浓度档位格","=SUM('配对统计'!K6:K440)"],
  ["浓度档位格覆盖率","=B19/B20"],
  ["基础模型列数",d.summary.core_model_columns],["基础模型矩阵秩",d.summary.core_model_rank],
  ["基础矩阵条件数",d.summary.core_condition_number],
  ["I指标（基础模型）",d.summary.core_I],
  ["随机档位I均值",d.summary.random_level_I_mean],
  ["模型I指标降低","=1-B25/B26"]
];
sh.getRange("A8:B27").values=metrics.map(([a,b])=>[a,typeof b==="string"?null:b]);
for(let i=0;i<metrics.length;i++)if(typeof metrics[i][1]==="string")sh.getRange("B"+(i+8)).formulas=[[metrics[i][1]]];
sh.getRange("B16").setNumberFormat("0.0%");
sh.getRange("B21").setNumberFormat("0.0%");
sh.getRange("B24:B26").setNumberFormat("0.0000");
sh.getRange("B27").setNumberFormat("0.0%");
const explanation=[
  ["范围","41种候选不删减；11种基底沿用均值；30种物质参与变量选择。"],
  ["组成选择","从27405个四元子集中，按配对覆盖优先、出现次数平衡选224个拟合组成。"],
  ["浓度选择","在所选组成内按基础模型的I准则搜索浓度档位，4次初始化加单行交换。"],
  ["拟合构成","85个单体浓度锚点、1个基底对照、224个四元配方，共310个。"],
  ["重复与验证","20次独立配制重复；20个未参与选点的留出验证组成。"],
  ["研究方式","跨组合的全局筛选设计；每个四元组成不单独拟合一套BBD曲面。"],
  ["模型范围","86列基础模型包含存在效应、条件对数浓度与单体曲率，不含全部配对交互。"],
  ["交互限制","加入435个存在交互后为521列、秩310；不能独立估计所有交互项。"],
  ["覆盖定义","100%是435个配对都出现；1341/3490个正浓度档位格被实测安排。"],
  ["统计指标","I为给定模型下的预测方差系数；不是实测感官预测误差。"],
  ["重新运行","浓度或候选范围变化后，应重跑算法；矩阵秩、I及档位格为本版快照。"]
];
sh.getRange("D5:E15").values=explanation;
sh.getRange("A8:B27").format.font={name:"Arial",size:11,color:"#1F2937"};
sh.getRange("D5:E15").format.font={name:"Arial",size:10,color:"#1F2937"};
sh.getRange("A5:A27").format.columnWidth=29;
sh.getRange("B5:B27").format.columnWidth=18;
sh.getRange("C1:C27").format.columnWidth=4;
sh.getRange("D5:D15").format.columnWidth=18;
sh.getRange("E5:E15").format.columnWidth=80;
sh.getRange("D5:E15").format.wrapText=true;
sh.getRange("D5:E15").format.rowHeight=42;
sh.getRange("A8:B27").format.rowHeight=26;

// Recalculate and verify numeric outputs against independently computed Python data.
wb.recalculate();
const actual=sh.getRange("B8:B27").values.flat();
const expected=[
  350,310,20,20,30,11,435,435,1,2,4,1341,3490,1341/3490,86,86,
  d.summary.core_condition_number,d.summary.core_I,d.summary.random_level_I_mean,
  d.summary.I_reduction_vs_random_mean
];
for(let i=0;i<expected.length;i++){
  if(typeof actual[i]!=="number" || Math.abs(actual[i]-expected[i])>1e-8*Math.max(1,Math.abs(expected[i])))
    throw new Error("Summary mismatch B"+(i+8)+": "+JSON.stringify({actual:actual[i],expected:expected[i]}));
}
for(let i=0;i<350;i++){
  const row=s["350配方"].getRange("M"+(i+6)+":P"+(i+6)).values[0];
  d.rows[i].concentrations.forEach((v,j)=>{
    if(Math.abs(row[j]-v)>1e-8*Math.max(1,v))throw new Error("Concentration mismatch "+i+" "+j);
  });
}
const scan=await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options:{useRegex:true,maxResults:30},summary:"formula scan",maxChars:1500});
console.log(scan.ndjson);
await fs.writeFile(path.join(outputDir,"formula_scan.txt"),scan.ndjson);
console.log(JSON.stringify({summary:actual,checked_concentration_rows:350}));

// Render every worksheet's main view.
const previews=path.join(outputDir,"preview");
await fs.mkdir(previews,{recursive:true});
for(const [name,range] of [
  ["方案总览","A1:E27"],["350配方","A2:P13"],["浓度矩阵","A2:J13"],
  ["浓度设置","A2:J13"],["配对统计","A2:L13"],["原始浓度","A2:J13"]]){
  const png=await wb.render({sheetName:name,range,scale:1.3,format:"png"});
  await fs.writeFile(path.join(previews,names.indexOf(name)+".png"),new Uint8Array(await png.arrayBuffer()));
}
const xlsx=await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(path.join(outputDir,"350次算法选组与浓度设计.xlsx"));
console.log("Workbook exported.");

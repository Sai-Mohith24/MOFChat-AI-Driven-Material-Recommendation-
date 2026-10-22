// MOFChat final-review deck (pptxgenjs). Run: node build.js
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const fs = require("fs");
const path = require("path");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const PROJ = "/Users/saimohith/Documents/Sem-5/Data-Driven/Final-project";
const OUT = process.argv[2] || "MOFChat_Final_Review.pptx";

const THEME = {
  name: "MOFChat Crystal Lattice",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0F2433", lt1: "FFFFFF", dk2: "1B3A4B", lt2: "F2F6F7",
    accent1: "0891B2", accent2: "D9622B", accent3: "5B6B73", accent4: "C5CFD3",
    accent5: "67D4E8", accent6: "F4A57C", hlink: "0891B2", folHlink: "5B6B73",
  },
};
const H = { navy: "0F2433", teal: "0891B2", copper: "D9622B", slate: "5B6B73", grey: "C5CFD3", lteal: "67D4E8", tint: "F2F6F7", tealTint: "E3F3F7", copTint: "FBEAE1" };

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "MOFChat - Final Review";
pres.author = "Team 09, 22AIE452";
pres.company = "Team 09";
const C = pres.SchemeColor;

// ---------- layouts ----------
const FOOT = "MOFChat  ·  Team 09  ·  22AIE452 Final Review";
pres.defineSlideMaster({
  title: "MOF_CONTENT",
  background: { color: "FFFFFF" },
  objects: [
    { text: { text: FOOT, options: { x: 0.6, y: 7.02, w: 8, h: 0.3, fontSize: 10, color: C.accent3, margin: 0 } } },
    { placeholder: { options: { name: "kicker", type: "body", x: 0.6, y: 0.32, w: 10, h: 0.32, fontSize: 12, bold: true, color: C.accent1, charSpacing: 2, margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.66, w: 12.1, h: 0.75, fontSize: 28, align: "left", bold: true, color: C.text1, fontFace: "Cambria", valign: "top", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 12.23, y: 7.02, w: 0.5, h: 0.3, fontSize: 10, color: C.accent3, align: "right" },
});
pres.defineSlideMaster({
  title: "MOF_DARK",
  background: { color: H.navy },
  objects: [],
});

// ---------- helpers ----------
async function icon(name, color = "FFFFFF", size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(fa[name], { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
const text = (s, t, o) => s.addText(t, Object.assign({ isTextBox: true, margin: 0, color: C.text1, fontSize: 15, valign: "top" }, o));
function content(kicker, title, section) {
  const s = pres.addSlide({ masterName: "MOF_CONTENT", sectionTitle: section });
  s.addText(kicker.toUpperCase(), { placeholder: "kicker" });
  s.addText(title, { placeholder: "title" });
  return s;
}
async function hexIcon(s, x, y, d, iconName, fill = C.accent1, name) {
  s.addShape(pres.shapes.HEXAGON, { x, y, w: d, h: d * 0.88, fill: { color: fill }, line: { color: fill, width: 0 }, objectName: name || "hex " + iconName });
  s.addImage({ data: await icon(iconName), x: x + d * 0.29, y: y + d * 0.88 / 2 - d * 0.21, w: d * 0.42, h: d * 0.42 });
}
function hexNum(s, x, y, d, label, fill = C.accent1, color = C.background1, fs = 16) {
  s.addShape(pres.shapes.HEXAGON, { x, y, w: d, h: d * 0.88, fill: { color: fill }, line: { color: fill, width: 0 } });
  text(s, label, { x, y, w: d, h: d * 0.88, align: "center", valign: "middle", bold: true, color, fontSize: fs, fontFace: "Cambria" });
}
function card(s, x, y, w, h, fill = C.background2, name) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: fill, width: 0 }, objectName: name || "card" });
}
function stat(s, x, y, w, num, label, color = C.accent1, numSize = 40) {
  text(s, num, { x, y, w, h: 0.75, fontSize: numSize, bold: true, color, fontFace: "Cambria", valign: "bottom" });
  text(s, label, { x, y: y + 0.8, w, h: 0.6, fontSize: 13, color: C.accent3 });
}
function bullets(s, items, o) {
  const runs = items.map((it, i) => {
    const arr = Array.isArray(it) ? it : [it];
    return arr.map((r, j) => {
      const isObj = typeof r === "object";
      const opts = Object.assign({}, isObj ? r.options : {});
      if (j === 0) Object.assign(opts, { bullet: { indent: 16 }, paraSpaceAfter: 8 });
      if (j === arr.length - 1 && i < items.length - 1) opts.breakLine = true;
      return { text: isObj ? r.text : r, options: opts };
    });
  }).flat();
  text(s, runs, Object.assign({ fontSize: 15 }, o));
}
const B = (t) => ({ text: t, options: { bold: true } });
function arrow(s, x1, y1, x2, y2, color = H.slate, head = true) {
  const flipH = x2 < x1, flipV = y2 < y1;
  s.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1), flipH, flipV, line: { color, width: 1.5, endArrowType: head ? "triangle" : undefined } });
}
function tableOpts(extra) {
  return Object.assign({ fontFace: "Calibri", fontSize: 13, color: H.navy, border: { type: "solid", pt: 0.75, color: "D5DEE2" }, margin: [3, 6, 3, 6], valign: "middle" }, extra);
}
const th = (t, o = {}) => ({ text: t, options: Object.assign({ bold: true, color: "FFFFFF", fill: { color: H.navy } }, o) });
const td = (t, o = {}) => ({ text: t, options: o });

function lattice(s, x0, y0, cols, rows, step, glow) {
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const x = x0 + c * step, y = y0 + r * step;
    if (c < cols - 1) s.addShape(pres.shapes.LINE, { x, y, w: step, h: 0, line: { color: "2E5266", width: 1.25 } });
    if (r < rows - 1) s.addShape(pres.shapes.LINE, { x, y, w: 0, h: step, line: { color: "2E5266", width: 1.25 } });
    if (c < cols - 1) s.addShape(pres.shapes.HEXAGON, { x: x + step / 2 - 0.09, y: y - 0.08, w: 0.18, h: 0.16, fill: { color: H.navy }, line: { color: "3B6A80", width: 1 } });
    if (r < rows - 1) s.addShape(pres.shapes.HEXAGON, { x: x - 0.09, y: y + step / 2 - 0.08, w: 0.18, h: 0.16, fill: { color: H.navy }, line: { color: "3B6A80", width: 1 } });
  }
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const x = x0 + c * step, y = y0 + r * step, g = glow.has(`${c},${r}`);
    const d = g ? 0.3 : 0.22;
    s.addShape(pres.shapes.OVAL, { x: x - d / 2, y: y - d / 2, w: d, h: d, fill: { color: g ? H.copper : "17394B" }, line: { color: g ? "F4A57C" : H.teal, width: 1.5 } });
  }
}

async function build() {
  // =============== 1. Title ===============
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "MOF_DARK", sectionTitle: "Introduction" });
  lattice(s, 8.3, 1.0, 5, 6, 1.0, new Set(["3,1", "4,1", "3,2", "1,4"]));
  text(s, "22AIE452  ·  DATA DRIVEN MATERIAL MODELING AND SIMULATION", { x: 0.7, y: 0.75, w: 7.4, h: 0.6, fontSize: 12, bold: true, color: C.accent5, charSpacing: 1.5 });
  text(s, [{ text: "MOF", options: { color: C.background1 } }, { text: "Chat", options: { color: C.accent6 } }], { x: 0.7, y: 1.55, w: 7.4, h: 1.3, fontSize: 66, bold: true, fontFace: "Cambria" });
  text(s, "Explainable, data-grounded metal-organic framework recommendation with validated LLM planning, multi-objective optimisation and surrogate models", { x: 0.7, y: 2.95, w: 7.0, h: 1.3, fontSize: 19, color: "D6E4EA" });
  text(s, "TEAM 09  ·  FINAL REVIEW", { x: 0.7, y: 4.65, w: 4, h: 0.3, fontSize: 12, bold: true, color: C.accent6, charSpacing: 2 });
  const team = [["Amrutha T", "24255"], ["Charan Tej Reddy Y", "24259"], ["Poojitha D", "24263"], ["Enku Sai Mohith", "24316"], ["Ramu Jahna Bindu", "24249"]];
  team.forEach(([n, r], i) => {
    const col = i < 3 ? 0 : 1, row = i < 3 ? i : i - 3;
    text(s, [{ text: n, options: { color: C.background1, bold: true } }, { text: "   " + r, options: { color: "9FB6C1" } }], { x: 0.7 + col * 3.5, y: 5.05 + row * 0.42, w: 3.4, h: 0.38, fontSize: 15 });
  });
  s.addNotes("Introduce the team and the project in one sentence: MOFChat is a conversational assistant that recommends metal-organic frameworks from the 12,020-MOF CoRE-MOF database, where every number in the answer is checked against the data. It builds on the ChatMOF paper and fixes the problems that paper reports.");

  // =============== 2. Outline ===============
  s = content("Overview", "Outline", "Introduction");
  const outline = [
    ["Problem and base paper", "MOF selection, ChatMOF and its limitations"],
    ["Literature and objectives", "What prior work gives us, what is missing"],
    ["Data and method", "CoRE-MOF ETL, architecture, planner, validator, models"],
    ["Results", "Benchmark, model comparison, surrogates, explanations"],
    ["Live application", "The Streamlit app and demo questions"],
    ["Lessons and conclusion", "What we learned, limits, future work"],
  ];
  outline.forEach(([h, d], i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.8 + col * 6.1, y = 1.8 + row * 1.65;
    hexNum(s, x, y, 0.95, String(i + 1).padStart(2, "0"), i === 3 ? C.accent2 : C.accent1);
    text(s, h, { x: x + 1.2, y: y + 0.02, w: 4.6, h: 0.42, fontSize: 20, bold: true, fontFace: "Cambria" });
    text(s, d, { x: x + 1.2, y: y + 0.46, w: 4.6, h: 0.5, fontSize: 15, color: C.accent3 });
  });
  s.addNotes("Six parts. The results section is the core: every number on those slides is produced by evaluate.py and recorded in docs/RESULTS.md.");

  // =============== 3. Motivation ===============
  s = content("01 · Introduction", "Choosing a MOF means searching thousands of structures at once", "Introduction");
  text(s, "Metal-organic frameworks are crystalline porous materials: metal nodes joined by organic linkers. Their tunable pores make them candidates for:", { x: 0.6, y: 1.75, w: 6.3, h: 0.9, fontSize: 16 });
  const apps = [["FaCloud", "CO₂ capture"], ["FaGasPump", "H₂ and CH₄ storage"], ["FaFilter", "Gas separation"], ["FaFlask", "Catalysis"]];
  for (let i = 0; i < apps.length; i++) {
    const y = 2.8 + i * 0.78;
    await hexIcon(s, 0.7, y, 0.6, apps[i][0], i % 2 ? C.accent2 : C.accent1);
    text(s, apps[i][1], { x: 1.5, y: y + 0.08, w: 4.5, h: 0.4, fontSize: 17, bold: true });
  }
  text(s, "A good choice needs database queries, several properties traded off together, and domain knowledge (which pore sizes admit which gases).", { x: 0.6, y: 6.0, w: 6.3, h: 0.8, fontSize: 14, color: C.accent3, italic: true });
  card(s, 7.4, 1.75, 5.3, 4.95);
  stat(s, 7.8, 1.95, 4.6, "12,020", "experimental MOFs in CoRE MOF 2019", C.accent1, 44);
  stat(s, 7.8, 3.5, 4.6, "65", "different metals across the structures", C.accent2, 44);
  stat(s, 7.8, 5.05, 4.6, "27 %", "have zero accessible surface area (pores too small for the N₂ probe)", C.accent1, 44);
  s.addNotes("MOFs are built from metal nodes and organic linkers. The database we use, CoRE MOF 2019, has 12,020 experimental structures with geometric descriptors computed by Zeo++. Picking one for, say, CO2 capture means filtering on several properties and ranking trade-offs, which is hard to do by hand.");

  // =============== 4. Base paper ===============
  s = content("01 · Base paper", "ChatMOF made MOF search conversational, but unchecked", "Introduction");
  card(s, 0.6, 1.75, 5.9, 4.95);
  text(s, "ChatMOF  (Kang & Kim, Nature Communications 15, 4705, 2024)", { x: 0.9, y: 1.95, w: 5.4, h: 0.6, fontSize: 15, bold: true });
  text(s, "A GPT-4 agent that plans tool calls: table search with LLM-written pandas code, MOFTransformer prediction, genetic-algorithm generation.", { x: 0.9, y: 2.6, w: 5.4, h: 1.1, fontSize: 15, color: C.accent3 });
  [["96.9 %", "search"], ["95.7 %", "prediction"], ["87.5 %", "generation"]].forEach(([n, l], i) => stat(s, 0.9 + i * 1.85, 3.75, 1.75, n, l, C.accent1, 30));
  text(s, "Our question: keep this convenience, but check every answer against the data.", { x: 0.9, y: 5.55, w: 5.4, h: 0.8, fontSize: 16, bold: true, color: C.accent2, fontFace: "Cambria" });
  text(s, "Reported accuracy on its own question sets", { x: 0.9, y: 5.05, w: 5.4, h: 0.4, fontSize: 12, color: C.accent3, italic: true });
  text(s, "Limitations reported in the paper", { x: 7.0, y: 1.75, w: 5.7, h: 0.45, fontSize: 18, bold: true, fontFace: "Cambria", color: C.accent2 });
  const lims = [["Token limits", "4 % of search tasks failed on large tables"], ["Logic errors", "in the code the LLM writes"], ["Proprietary LLM", "needs online GPT-4"], ["One model per property", "a pretrained network for each target"], ["No validation", "final answers are not checked against data"]];
  lims.forEach(([h, d], i) => {
    const y = 2.35 + i * 0.85;
    hexNum(s, 7.0, y, 0.55, String(i + 1), C.accent2, C.background1, 13);
    text(s, [B(h), { text: "  " + d, options: { color: C.accent3 } }], { x: 7.75, y: y + 0.05, w: 4.95, h: 0.6, fontSize: 15 });
  });
  s.addNotes("ChatMOF is our base paper. It is impressive, but its own analysis lists these problems: token-limit failures, logic errors in generated code, dependence on GPT-4, a separate pretrained model per property, and no validation of the final answer. Each of these is a design goal for MOFChat.");

  // =============== 5. Literature ===============
  pres.addSection({ title: "Literature" });
  s = content("02 · Literature review", "Prior work gives the parts; none checks LLM answers against data", "Literature");
  const lit = [
    ["ChatMOF", "Kang & Kim, Nat. Commun. 2024", "LLM agent for MOF search", "Base paper; same 12,020-MOF table"],
    ["MOFTransformer", "Kang et al., Nat. Mach. Intell. 2023", "Pretrained MOF property model", "We predict from descriptors, no 3D files"],
    ["CoRE MOF 2019", "Chung et al., J. Chem. Eng. Data 2019", "Curated MOF structures + Zeo++", "Our dataset; ETL verifies it"],
    ["FT-Transformer", "Gorishniy et al., NeurIPS 2021", "Transformer for tabular data", "Our embedding + regressor backbone"],
    ["Trees vs deep learning", "Grinsztajn et al., NeurIPS 2022", "GBDT still strong on tables", "Why we compare XGBoost vs FT"],
    ["RAG / TableRAG / Chain-of-Table", "Lewis 2020; Chen 2024; Wang 2024", "LLMs over text and tables", "SQL for numbers, RAG for knowledge"],
    ["NSGA-II", "Deb et al., IEEE TEVC 2002", "Non-dominated sorting", "Multi-objective MOF ranking"],
    ["SHAP", "Lundberg & Lee, NeurIPS 2017", "Shapley explanations", "Explains every prediction"],
  ];
  s.addTable([[th("Work"), th("Reference"), th("Idea"), th("How MOFChat uses it")], ...lit.map((r, i) => r.map((c, j) => td(c, Object.assign({ fill: { color: i % 2 ? "FFFFFF" : H.tint } }, j === 0 ? { bold: true } : {}))))],
    tableOpts({ x: 0.6, y: 1.7, w: 12.1, colW: [2.6, 3.4, 2.8, 3.3], rowH: 0.5 }));
  text(s, "All 15 references verified against publisher or arXiv records; full table in docs/LITERATURE_REVIEW.md", { x: 0.6, y: 6.45, w: 12, h: 0.35, fontSize: 12, color: C.accent3, italic: true });
  s.addNotes("Eight of the fifteen verified papers. The point to make: each paper gives us one building block, but no prior system validates the language model's final answer against the database. That gap is MOFChat's contribution.");

  // =============== 6. Gap & objectives ===============
  s = content("02 · Research gap", "Objectives: exact, verifiable answers using free or local models", "Literature");
  card(s, 0.6, 1.75, 4.6, 4.95, H.navy);
  text(s, "THE GAP", { x: 0.95, y: 2.0, w: 4, h: 0.35, fontSize: 13, bold: true, color: C.accent6, charSpacing: 2 });
  text(s, "LLM agents make MOF search conversational, but they write code that can fail, depend on paid models and return numbers nobody checks.", { x: 0.95, y: 2.5, w: 3.95, h: 2.2, fontSize: 19, color: C.background1, fontFace: "Cambria" });
  text(s, "We want the convenience of ChatMOF with the reliability of a database query.", { x: 0.95, y: 5.0, w: 3.95, h: 1.2, fontSize: 15, color: "C9D9E0", italic: true });
  const objs = [
    ["Exact answers", "over all 12,020 MOFs, with free or local LLMs"],
    ["Safe LLM planning", "validation, self-correction and fallback"],
    ["Multi-objective ranking", "NSGA-II over several properties"],
    ["Predictions you can trust", "uncertainty intervals and SHAP explanations"],
    ["Domain knowledge", "retrieval over notes and the ChatMOF paper"],
    ["Measured, not claimed", "labelled benchmark plus a held-out set"],
  ];
  objs.forEach(([h, d], i) => {
    const y = 1.78 + i * 0.82;
    hexNum(s, 5.7, y, 0.6, String(i + 1), C.accent1, C.background1, 14);
    text(s, h, { x: 6.5, y: y + 0.0, w: 6.2, h: 0.35, fontSize: 17, bold: true });
    text(s, d, { x: 6.5, y: y + 0.36, w: 6.2, h: 0.35, fontSize: 14, color: C.accent3 });
  });
  s.addNotes("Six objectives. The last one matters most for a review: we do not just claim the system works, we measure it on 64 labelled questions and on 20 held-out questions written after tuning.");

  // =============== 7. Review 1 -> final ===============
  pres.addSection({ title: "Method" });
  s = content("03 · From review 1", "Review 1 failed: similarity search cannot satisfy number filters", "Method");
  card(s, 0.6, 1.75, 5.85, 3.95, H.copTint);
  text(s, "REVIEW 1: TWO-TOWER RETRIEVAL", { x: 0.9, y: 1.95, w: 5.3, h: 0.35, fontSize: 13, bold: true, color: C.accent2, charSpacing: 1 });
  bullets(s, ["FT-Transformer autoencoder indexed the MOFs", "Sentence-BERT embedded the question", "Same vector size, but never trained together, so retrieval ignored the question", "\"Surface area > 4000\" is a filter, not a similarity"], { x: 0.9, y: 2.45, w: 5.3, h: 2.4 });
  stat(s, 0.9, 4.2, 2.6, "9.4 %", "dev set exact", C.accent2, 34);
  stat(s, 3.4, 4.2, 2.6, "5 %", "held-out exact", C.accent2, 34);
  card(s, 6.9, 1.75, 5.85, 3.95, H.tealTint);
  text(s, "FINAL: PLAN → VALIDATE → QUERY", { x: 7.2, y: 1.95, w: 5.3, h: 0.35, fontSize: 13, bold: true, color: C.accent1, charSpacing: 1 });
  bullets(s, ["The LLM writes a structured JSON plan, never code", "A validator checks and repairs the plan", "Exact SQL filters; NSGA-II ranks", "FT-Transformer kept for similarity, where it fits"], { x: 7.2, y: 2.45, w: 5.3, h: 2.4 });
  stat(s, 7.2, 4.2, 2.6, "100 %", "dev set exact", C.accent1, 34);
  stat(s, 9.7, 4.2, 2.6, "100 %", "held-out exact", C.accent1, 34);
  arrow(s, 6.47, 3.72, 6.88, 3.72, H.slate);
  text(s, "Lesson: constraint satisfaction over numbers is a database problem, not a similarity problem.", { x: 0.6, y: 6.05, w: 12.1, h: 0.45, fontSize: 15, italic: true, color: C.text2 });
  s.addNotes("At review 1 we searched an FT-Transformer index with a Sentence-BERT question vector. The two vectors had the same size but no shared training, so the retrieved MOFs did not depend on the question. It scored 9.4% on our benchmark. The rebuilt system plans, validates and queries, and reaches 100% on both sets with the default model.");

  // =============== 8. Data ===============
  s = content("04 · Dataset", "CoRE MOF 2019: 12,020 MOFs, checked before any modelling", "Method");
  const etl = [
    ["Missing values, duplicate rows or names", "none", "-"],
    ["Two column pairs identical", "duplicates", "dropped"],
    ["Pore volume = void fraction / density", "derived (error 6×10⁻⁶)", "documented"],
    ["Zero surface area (3,252 MOFs)", "all have PLD < 3.31 Å", "physics rule"],
    ["Density header says cm³/g", "values are g/cm³", "label fixed"],
    ["2,087 multi-metal MOFs", "comma-separated metals", "mof_metals table"],
  ];
  s.addTable([[th("Check"), th("Finding"), th("Action")], ...etl.map((r, i) => r.map((c) => td(c, { fill: { color: i % 2 ? "FFFFFF" : H.tint } })))],
    tableOpts({ x: 0.6, y: 1.75, w: 7.6, colW: [3.5, 2.4, 1.7], rowH: 0.64, fontSize: 14 }));
  card(s, 8.7, 1.75, 4.0, 4.48);
  await hexIcon(s, 9.0, 2.0, 0.75, "FaDatabase", C.accent1);
  text(s, "data/coremof.db", { x: 9.95, y: 2.15, w: 2.7, h: 0.4, fontSize: 16, bold: true, fontFace: "Courier New" });
  bullets(s, [[B("materials"), " – 15 columns, indexed"], [B("mof_metals"), " – one row per metal"], [B("columns_doc"), " – units and meaning"]], { x: 9.0, y: 3.0, w: 3.5, h: 1.6, fontSize: 15 });
  text(s, "Zeo++ geometry, 3.31 Å N₂ probe. No gas-uptake labels in this table.", { x: 9.0, y: 4.75, w: 3.5, h: 1.2, fontSize: 14, color: C.accent3, italic: true });
  s.addNotes("setup_db.py loads the ChatMOF descriptor table and asserts each of these facts. Key one: the 3,252 MOFs with zero surface area are not missing data. All of them have a pore limiting diameter below the 3.31 Angstrom probe, so the probe cannot enter. We turn that into an exact physics rule in the surrogate model.");

  // =============== 9. Architecture ===============
  s = content("05 · System design", "The LLM only plans and writes; everything else is checked code", "Method");
  const box = (x, y, w, h, title, sub, llm) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: llm ? H.copTint : H.tealTint }, line: { color: llm ? H.copper : H.teal, width: 1.25 }, objectName: "box " + title });
    text(s, [{ text: title, options: { bold: true, breakLine: true, fontSize: 15 } }, { text: sub, options: { fontSize: 12, color: C.accent3 } }], { x: x + 0.12, y, w: w - 0.24, h, align: "center", valign: "middle" });
  };
  box(0.6, 1.75, 2.2, 0.95, "Question", "plain English", false);
  box(3.25, 1.75, 2.9, 0.95, "Planner", "LLM JSON plan + rule parser", true);
  box(6.6, 1.75, 2.9, 0.95, "Plan validator", "columns, units, ranges, grounding", false);
  box(9.95, 1.75, 2.75, 0.95, "Intent router", "search · similar · predict · knowledge", false);
  arrow(s, 2.8, 2.22, 3.25, 2.22); arrow(s, 6.15, 2.22, 6.6, 2.22); arrow(s, 9.5, 2.22, 9.95, 2.22);
  // retry loop
  s.addShape(pres.shapes.LINE, { x: 8.05, y: 2.7, w: 0, h: 0.32, line: { color: H.copper, width: 1.5, dashType: "dash" } });
  s.addShape(pres.shapes.LINE, { x: 4.7, y: 3.02, w: 3.35, h: 0, line: { color: H.copper, width: 1.5, dashType: "dash" } });
  arrow(s, 4.7, 3.02, 4.7, 2.7, H.copper);
  text(s, "errors → self-correct up to 2×", { x: 4.85, y: 3.06, w: 3.1, h: 0.3, fontSize: 12, color: C.accent2, italic: true, align: "center" });
  // bus to branches
  s.addShape(pres.shapes.LINE, { x: 11.32, y: 2.7, w: 0, h: 0.72, line: { color: H.slate, width: 1.5 } });
  s.addShape(pres.shapes.LINE, { x: 2.03, y: 3.42, w: 9.29, h: 0, line: { color: H.slate, width: 1.5 } });
  const br = [["SQL + NSGA-II", "read-only, parameterised; closest match if none"], ["Similarity", "FT-Transformer embeddings + FAISS"], ["Prediction", "XGBoost + conformal interval + SHAP"], ["Knowledge", "RAG over notes + ChatMOF paper"]];
  br.forEach(([t, d], i) => {
    const x = 0.6 + i * 3.08;
    arrow(s, x + 1.43, 3.42, x + 1.43, 3.65);
    box(x, 3.65, 2.86, 1.1, t, d, false);
    s.addShape(pres.shapes.LINE, { x: x + 1.43, y: 4.75, w: 0, h: 0.3, line: { color: H.slate, width: 1.5 } });
  });
  s.addShape(pres.shapes.LINE, { x: 2.03, y: 5.05, w: 9.24, h: 0, line: { color: H.slate, width: 1.5 } });
  arrow(s, 2.4, 5.05, 2.4, 5.35);
  box(0.6, 5.35, 3.6, 0.95, "Answer writer", "LLM, from at most 10 verified rows", true);
  box(4.65, 5.35, 3.9, 0.95, "Answer validator", "IDs, numbers and claims must match data", false);
  box(9.0, 5.35, 3.7, 0.95, "Answer + verified table", "plus plan, SQL and validator trace", false);
  arrow(s, 4.2, 5.82, 4.65, 5.82); arrow(s, 8.55, 5.82, 9.0, 5.82);
  s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 6.5, w: 0.25, h: 0.2, fill: { color: H.copTint }, line: { color: H.copper, width: 1 } });
  text(s, "uses a language model", { x: 0.95, y: 6.47, w: 2.6, h: 0.3, fontSize: 12, color: C.accent3 });
  s.addShape(pres.shapes.RECTANGLE, { x: 3.6, y: 6.5, w: 0.25, h: 0.2, fill: { color: H.tealTint }, line: { color: H.teal, width: 1 } });
  text(s, "deterministic, tested code", { x: 3.95, y: 6.47, w: 3, h: 0.3, fontSize: 12, color: C.accent3 });
  s.addNotes("Walk the diagram left to right. Only the two orange boxes use a language model. The plan is validated and sent back for correction up to twice; then the router picks one of four tools. The answer writer sees at most 10 verified rows, so token limits never occur, and the answer validator checks the text before it is shown.");

  // =============== 10. Planner + validator ===============
  s = content("05 · Planning", "The LLM writes a plan, not code, and the validator repairs it", "Method");
  card(s, 0.6, 1.75, 6.6, 0.75, H.tint);
  await hexIcon(s, 0.8, 1.83, 0.6, "FaCommentDots", C.accent2);
  text(s, "“Which zinc MOFs have high surface area and low density?”", { x: 1.6, y: 1.75, w: 5.5, h: 0.75, fontSize: 16, italic: true, valign: "middle" });
  arrow(s, 3.9, 2.5, 3.9, 2.8);
  card(s, 0.6, 2.8, 6.6, 1.95, H.navy);
  text(s, '{ "intent": "search",\n  "metals": ["Zn"],\n  "objectives": [\n    {"column": "Surface_Area", "direction": "max"},\n    {"column": "Density", "direction": "min"} ],\n  "limit": 5 }', { x: 0.9, y: 2.95, w: 6.1, h: 2.1, fontSize: 13, fontFace: "Courier New", color: "D6E4EA" });
  arrow(s, 3.9, 4.75, 3.9, 5.05);
  card(s, 0.6, 5.05, 6.6, 1.65, H.tealTint);
  text(s, [B("Executor: "), { text: "whitelisted columns, bound parameters, read-only connection. Two objectives, so NSGA-II ranks the zinc MOFs." }], { x: 0.85, y: 5.15, w: 6.1, h: 0.75, fontSize: 14 });
  text(s, "SELECT * FROM materials WHERE MOF_ID IN\n  (SELECT MOF_ID FROM mof_metals WHERE Metal IN (?))", { x: 0.85, y: 5.95, w: 6.1, h: 0.6, fontSize: 12, fontFace: "Courier New", color: C.text2 });
  text(s, "Validator checks", { x: 7.7, y: 1.75, w: 5, h: 0.45, fontSize: 18, bold: true, fontFace: "Cambria" });
  const checks = ["Column aliases resolved from one registry", "Units, operators and percentages normalised", "Impossible or invented values rejected", "Thresholds not in the question become preferences", "MOF IDs not in the question dropped", "Superlatives written as constraints repaired", "Application presets expanded and explained"];
  for (let i = 0; i < checks.length; i++) {
    const y = 2.3 + i * 0.56;
    s.addImage({ data: await icon("FaCheckCircle", H.teal), x: 7.75, y: y + 0.05, w: 0.28, h: 0.28 });
    text(s, checks[i], { x: 8.2, y, w: 4.5, h: 0.45, fontSize: 15, valign: "middle" });
  }
  text(s, "Hybrid planner: facts the rule parser is certain of (numbers, metals, limits) are merged into the LLM plan.", { x: 7.7, y: 6.25, w: 5.0, h: 0.6, fontSize: 13, italic: true, color: C.accent3 });
  s.addNotes("This is a real plan for the demo question. The LLM fills a fixed JSON schema at temperature 0. The validator checks it; if there are errors they go back to the LLM up to twice, and then the rule-parser plan is used. The executor turns the plan into SQL using only whitelisted column names.");

  // =============== 11. LLM layer ===============
  s = content("05 · Language models", "14 free or local models behind one interface, with fallback", "Method");
  const prov = [["Google Gemini", "3.1 Flash-Lite, 3.5 Flash, 3.8 Flash, Flash-Lite latest", "~10–15 req/min"], ["Groq", "GPT-OSS 120B, GPT-OSS 20B, Qwen 3.8 27B", "8,000 tokens/min"], ["OpenRouter", "Nemotron 3 Super / Ultra, Gemma 4 31B", "~50 req/day"], ["Ollama (offline)", "Llama 3 8B, Llama 3.1 8B, Qwen 2.5 7B, Nemotron Mini", "none, laptop CPU"]];
  s.addTable([[th("Provider"), th("Models"), th("Free limit")], ...prov.map((r, i) => r.map((c, j) => td(c, Object.assign({ fill: { color: i % 2 ? "FFFFFF" : H.tint } }, j === 0 ? { bold: true } : {}))))],
    tableOpts({ x: 0.6, y: 1.75, w: 7.4, colW: [1.9, 3.8, 1.7], rowH: 0.62, fontSize: 14 }));
  text(s, "Each call is throttled to its free-tier budget. A rate limit or outage (429 / 503) moves the call to the next model.", { x: 0.6, y: 4.98, w: 7.4, h: 0.6, fontSize: 14, color: C.accent3 });
  [["14", "models"], ["4", "providers"], ["0", "paid APIs"]].forEach(([n, l], i) => stat(s, 0.6 + i * 2.5, 5.65, 2.3, n, l, i === 2 ? C.accent2 : C.accent1, 30));
  text(s, "Default fallback chain", { x: 8.6, y: 1.75, w: 4.1, h: 0.45, fontSize: 18, bold: true, fontFace: "Cambria" });
  const chain = [["Gemini 3.1 Flash-Lite", "best held-out score", C.accent1], ["GPT-OSS 120B (Groq)", "0 provider errors", C.accent1], ["Qwen 3.8 27B (Groq)", "", C.accent1], ["Llama 3 8B (local)", "works offline", C.accent2], ["Rule parser + template", "always answers", C.accent3]];
  chain.forEach(([n, d], i) => {
    const y = 2.35 + i * 0.86;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.6, y, w: 4.1, h: 0.62, rectRadius: 0.08, fill: { color: chain[i][2] }, line: { color: chain[i][2], width: 0 } });
    text(s, [{ text: n, options: { bold: true } }, { text: d ? "   " + d : "", options: { fontSize: 12, color: "E6F1F4" } }], { x: 8.8, y, w: 3.8, h: 0.62, fontSize: 15, color: C.background1, valign: "middle" });
    if (i < chain.length - 1) arrow(s, 10.65, y + 0.62, 10.65, y + 0.86, H.slate);
  });
  s.addNotes("The language model is a swappable part. mofchat/llm.py has a registry of 14 models from four providers; each reports whether it is usable right now. If every model fails, the rule parser plans and a template writes the answer, so a question is never left unanswered.");

  // =============== 12. NSGA-II ===============
  s = content("05 · Optimisation", "NSGA-II ranks candidates on several objectives at once", "Method");
  bullets(s, [
    [B("One objective"), " → plain sort"],
    [B("Two or more"), " → fast non-dominated sorting (exact O(n log n) sweep for two objectives) + crowding distance"],
    [B("Screening"), " → candidates in the worst 25 % of any objective removed first"],
    [B("No exact match"), " → closest MOFs by total constraint violation, and the user is told"],
    [B("Speed"), " → all 12,020 MOFs in 0.02 s (2 objectives), 2.6 s (3)"],
  ], { x: 0.6, y: 1.8, w: 5.6, h: 3.6, fontSize: 15 });
  const presets = [["H₂ storage", "PLD ≥ 2.89 Å; max surface area, void fraction"], ["CH₄ storage", "PLD ≥ 3.80 Å; max volumetric area, void fraction"], ["CO₂ capture", "open metal site; PLD ≥ 3.30 Å; min LCD"]];
  s.addTable([[th("Preset"), th("Constraints and objectives")], ...presets.map((r, i) => r.map((c, j) => td(c, Object.assign({ fill: { color: i % 2 ? "FFFFFF" : H.tint } }, j === 0 ? { bold: true } : {}))))],
    tableOpts({ x: 0.6, y: 5.15, w: 5.6, colW: [1.45, 4.15], rowH: 0.38, fontSize: 12 }));
  const P = JSON.parse(fs.readFileSync(path.join(__dirname, "pareto.json")));
  const xs = [...P.bg.map((p) => p[0]), ...P.f23.map((p) => p[0]), ...P.f1.map((p) => p[0])];
  const nb = P.bg.length, n2 = P.f23.length, n1 = P.f1.length;
  const pad = (arr, before, after) => [...Array(before).fill(null), ...arr, ...Array(after).fill(null)];
  s.addChart(pres.charts.SCATTER, [
    { name: "X", values: xs },
    { name: "Candidates (sample of 700)", values: pad(P.bg.map((p) => p[1]), 0, n2 + n1) },
    { name: "Pareto fronts 2–3", values: pad(P.f23.map((p) => p[1]), nb, n1) },
    { name: "Front 1 (recommended)", values: pad(P.f1.map((p) => p[1]), nb + n2, 0) },
  ], {
    x: 6.6, y: 1.65, w: 6.2, h: 5.15, lineSize: 0, lineDataSymbol: "circle", lineDataSymbolSize: 6,
    chartColors: [H.grey, H.teal, H.copper], showLegend: true, legendPos: "b", legendFontSize: 12, legendFontFace: "+mn-lt", legendColor: H.slate,
    showTitle: true, title: "H₂ storage: 10,226 MOFs with PLD ≥ 2.89 Å", titleFontSize: 14, titleFontFace: "+mn-lt", titleColor: H.navy,
    showValAxisTitle: true, valAxisTitle: "Void fraction", valAxisTitleFontSize: 12, valAxisTitleColor: H.slate, valAxisTitleFontFace: "+mn-lt", valAxisMinVal: 0, valAxisMaxVal: 1,
    showCatAxisTitle: true, catAxisTitle: "Gravimetric surface area (m²/g)", catAxisTitleFontSize: 12, catAxisTitleColor: H.slate, catAxisTitleFontFace: "+mn-lt", catAxisMinVal: 0, catAxisMaxVal: 9000,
    catAxisLabelColor: H.slate, valAxisLabelColor: H.slate, catAxisLabelFontSize: 11, valAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
    valGridLine: { color: "E3E9EC", size: 0.5 }, catGridLine: { style: "none" }, valAxisLabelFormatCode: "0.0", catAxisLabelFormatCode: "#,##0",
  });
  s.addNotes("For multi-objective questions we use NSGA-II's selection step: non-dominated sorting plus crowding distance. The chart is the real data for the hydrogen-storage preset: grey points are a sample of candidates, orange are the first Pareto front, teal the next two fronts. Application presets are explicit heuristics, because the dataset has no adsorption data.");

  // =============== 13. Surrogates + FT ===============
  s = content("05 · Models", "Surrogates predict properties; an FT-Transformer powers similarity", "Method");
  text(s, "FT-Transformer (Gorishniy et al., 2021)", { x: 0.6, y: 1.75, w: 6, h: 0.45, fontSize: 18, bold: true, fontFace: "Cambria" });
  const tok = ["[CLS]", "density", "LCD", "PLD", "LFPD", "VF", "metal", "OMS"];
  tok.forEach((t, i) => {
    const x = 0.6 + i * 0.74;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.6, w: 0.66, h: 0.5, rectRadius: 0.06, fill: { color: i === 0 ? H.copper : i > 5 ? H.navy : H.teal }, line: { width: 0, color: "FFFFFF" } });
    text(s, t, { x, y: 5.6, w: 0.66, h: 0.5, fontSize: 10, bold: true, color: C.background1, align: "center", valign: "middle" });
  });
  text(s, "numeric tokens  x·Wⱼ + bⱼ   ·   categorical embeddings", { x: 0.6, y: 6.18, w: 6, h: 0.3, fontSize: 12, color: C.accent3 });
  arrow(s, 3.5, 5.6, 3.5, 5.25);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.9, y: 4.05, w: 5.3, h: 1.2, rectRadius: 0.08, fill: { color: H.tealTint }, line: { color: H.teal, width: 1.25 } });
  text(s, [{ text: "3 pre-norm Transformer blocks", options: { bold: true, breakLine: true } }, { text: "d = 64, 4 heads, attention maps returned", options: { fontSize: 13, color: C.accent3 } }], { x: 0.9, y: 4.05, w: 5.3, h: 1.2, align: "center", valign: "middle", fontSize: 15 });
  arrow(s, 2.1, 4.05, 2.1, 3.7); arrow(s, 5.0, 4.05, 5.0, 3.7);
  card(s, 0.6, 2.35, 3.0, 1.35, H.copTint);
  text(s, [{ text: "Self-supervised embedding", options: { bold: true, breakLine: true } }, { text: "30 % tokens masked; [CLS] rebuilds all 10. 114k params → FAISS", options: { fontSize: 12, color: C.accent3 } }], { x: 0.75, y: 2.4, w: 2.75, h: 1.25, fontSize: 14, valign: "middle" });
  card(s, 3.8, 2.35, 2.7, 1.35, H.copTint);
  text(s, [{ text: "Regression head", options: { bold: true, breakLine: true } }, { text: "same backbone, a second opinion on predictions", options: { fontSize: 12, color: C.accent3 } }], { x: 3.95, y: 2.4, w: 2.45, h: 1.25, fontSize: 14, valign: "middle" });
  text(s, "Surrogate property models", { x: 7.2, y: 1.75, w: 5.5, h: 0.45, fontSize: 18, bold: true, fontFace: "Cambria" });
  const sur = [["FaBullseye", "Targets", "accessible surface area; void fraction (pore volume excluded to avoid leakage)"], ["FaRandom", "Split", "70 / 10 / 10 / 10: train, early stopping, conformal calibration, test"], ["FaLayerGroup", "Models", "mean baseline, Ridge, Gaussian process, XGBoost (main), FT-Transformer"], ["FaAtom", "Physics rule", "PLD below the 3.31 Å probe → surface area exactly 0"], ["FaBalanceScale", "Trust", "split-conformal 90 % intervals and TreeSHAP explanations"]];
  for (let i = 0; i < sur.length; i++) {
    const y = 2.35 + i * 0.88;
    await hexIcon(s, 7.2, y, 0.6, sur[i][0], i === 3 ? C.accent2 : C.accent1);
    text(s, [B(sur[i][1] + "  "), { text: sur[i][2], options: { color: C.accent3 } }], { x: 8.0, y: y - 0.02, w: 4.7, h: 0.8, fontSize: 14 });
  }
  s.addNotes("Left: the FT-Transformer turns each descriptor into a token, adds a CLS token, and runs three Transformer blocks. Trained self-supervised by masking 30% of tokens, its CLS state becomes a MOF embedding for similarity search. Right: the surrogate setup. The physics rule makes zero surface areas exact, and conformal calibration gives intervals with guaranteed coverage.");

  // =============== 14. RAG + answer validator ===============
  s = content("05 · Grounding", "Retrieval adds knowledge; a validator keeps the LLM honest", "Method");
  card(s, 0.6, 1.75, 5.2, 4.95, H.tint);
  await hexIcon(s, 0.9, 2.0, 0.7, "FaBook", C.accent1);
  text(s, "Knowledge retrieval (RAG)", { x: 1.8, y: 2.1, w: 3.9, h: 0.45, fontSize: 18, bold: true, fontFace: "Cambria" });
  bullets(s, ["5 curated, referenced notes + the ChatMOF paper → 104 chunks", "all-MiniLM-L6-v2 embeddings, FAISS inner product", "Best match below 0.30 cosine → treated as off-topic", "Sources are shown with every answer"], { x: 0.9, y: 2.95, w: 4.7, h: 2.4, fontSize: 15 });
  [["75 %", "hit@1"], ["83 %", "hit@3"], ["5 / 5", "off-topic rejected"]].forEach(([n, l], i) => stat(s, 0.9 + i * 1.6, 5.2, 1.55, n, l, C.accent1, 26));
  text(s, "Answer validator", { x: 6.3, y: 1.75, w: 6.4, h: 0.45, fontSize: 18, bold: true, fontFace: "Cambria" });
  const av = [["Extract", "every MOF ID and number, incl. “8 318”-style thousands"], ["Correct", "IDs within edit distance 2 (ACOCLUS → ACOCUS)"], ["Trace", "each number must match the data within rounding"], ["Check claims", "“A, B, C have ≥ 6000 m²/g”, “on the first Pareto front”"], ["Regenerate", "once, listing the exact problems"], ["Flag", "anything still unverified, above the verified table"]];
  av.forEach(([h, d], i) => {
    const y = 2.3 + i * 0.73;
    hexNum(s, 6.3, y, 0.55, String(i + 1), i === 3 ? C.accent2 : C.accent1, C.background1, 13);
    text(s, [B(h + "  "), { text: d, options: { color: C.accent3 } }], { x: 7.05, y: y + 0.03, w: 5.65, h: 0.55, fontSize: 15, valign: "middle" });
  });
  s.addNotes("Step 4 was added after testing the app: a sentence like 'A, B and C all have surface areas of at least 6000' passes a simple number check, because 6000 appears somewhere, but it is false if B has 4,564. The validator now looks up each named MOF and checks the claim, including Pareto-front claims against the NSGA-II ranks.");

  // =============== 15. Benchmark ===============
  pres.addSection({ title: "Results" });
  s = content("06 · Results", "Exact answers jump from 5 % to 100 % on held-out questions", "Results");
  s.addChart(pres.charts.BAR, [
    { name: "Development set (64 questions)", labels: ["Review-1 two-tower", "Rules only (no LLM)", "LLM single shot", "LLM + validator", "Hybrid (default)"], values: [9.4, 100, 100, 100, 100] },
    { name: "Held-out set (20 questions)", labels: ["Review-1 two-tower", "Rules only (no LLM)", "LLM single shot", "LLM + validator", "Hybrid (default)"], values: [5, 80, 100, 100, 100] },
  ], {
    x: 0.5, y: 1.65, w: 8.2, h: 5.15, barDir: "col", barGapWidthPct: 60, chartColors: [H.grey, H.teal],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelColor: H.navy, dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "General\"%\"",
    showLegend: true, legendPos: "t", legendFontSize: 12, legendFontFace: "+mn-lt", legendColor: H.slate,
    showTitle: true, title: "Exact answer match (%), LLM = Gemini 3.1 Flash-Lite", titleFontSize: 14, titleFontFace: "+mn-lt", titleColor: H.navy,
    valAxisMaxVal: 110, valAxisMinVal: 0, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    catAxisLabelColor: H.slate, catAxisLabelFontSize: 12, catAxisLabelFontFace: "+mn-lt",
  });
  card(s, 9.1, 1.75, 3.6, 4.95);
  text(s, "How to read it", { x: 9.4, y: 1.95, w: 3.1, h: 0.4, fontSize: 17, bold: true, fontFace: "Cambria" });
  bullets(s, [[B("Exact"), " = same MOFs (or count) as the hand-written gold plan"], [B("Dev 100 % is optimistic"), " for rules: they were tuned on it"], [B("Held-out"), " phrasings were written later, never tuned on"], [B("ChatMOF"), " reports 96.9 % on its own search set (different questions)"]], { x: 9.4, y: 2.5, w: 3.1, h: 4.0, fontSize: 14 });
  s.addNotes("A system counts as correct only if it returns exactly the gold MOFs. The held-out set is the honest estimate: 20 phrasings like 'tops 5500' or 'lighter than 0.4' written after the rule parser was finished. Review 1 gets 5%, rules alone 80%, and the default system 100%. Caveat: 20 questions, so one question is 5 points.");

  // =============== 16. Ablation ===============
  s = content("06 · Ablation", "Validation and the hybrid planner make a small offline LLM usable", "Results");
  s.addChart(pres.charts.BAR, [
    { name: "Held-out set", labels: ["Llama 3 8B alone", "+ validator", "+ hybrid planner"], values: [65, 70, 80] },
    { name: "Development set", labels: ["Llama 3 8B alone", "+ validator", "+ hybrid planner"], values: [85.9, 93.8, 100] },
  ], {
    x: 0.5, y: 1.65, w: 7.2, h: 5.15, barDir: "col", barGapWidthPct: 60, chartColors: [H.copper, H.grey],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelColor: H.navy, dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "General\"%\"",
    showLegend: true, legendPos: "t", legendFontSize: 12, legendFontFace: "+mn-lt", legendColor: H.slate,
    showTitle: true, title: "Exact answer match (%), local Llama 3 8B via Ollama", titleFontSize: 14, titleFontFace: "+mn-lt", titleColor: H.navy,
    valAxisMaxVal: 110, valAxisMinVal: 0, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    catAxisLabelColor: H.slate, catAxisLabelFontSize: 12, catAxisLabelFontFace: "+mn-lt",
  });
  stat(s, 8.2, 1.75, 4.5, "+15 pts", "held-out accuracy added by the safety layers, fully offline", C.accent2, 48);
  stat(s, 8.2, 3.35, 4.5, "< 0.01 s", "added by validation and the hybrid merge", C.accent1, 40);
  text(s, "With a strong cloud model the layers change nothing (100 → 100 → 100 %); they are insurance.", { x: 8.2, y: 5.0, w: 4.5, h: 0.8, fontSize: 14, color: C.accent3 });
  text(s, "Remaining Llama errors: “natural gas” mapped to H₂, one extra objective, a count instead of a search.", { x: 8.2, y: 5.85, w: 4.5, h: 0.9, fontSize: 14, color: C.accent3, italic: true });
  s.addNotes("This is the ablation. A local 8-billion-parameter model gets 65% alone on held-out questions; the validator lifts it to 70% and the hybrid merge to 80%. For a strong cloud model these layers change nothing, which is the point: they cost almost nothing and protect us when the model is weak or offline.");

  // =============== 17. Model comparison ===============
  s = content("06 · Model comparison", "Free cloud models tie on accuracy; reliability and speed differ", "Results");
  const mc = [
    ["Gemini 3.1 Flash-Lite (default)", "100 %", "100 %", "100 %", "1.5 s", "13 / 84"],
    ["GPT-OSS 120B (Groq)", "95 %", "95 %", "100 %", "2.4–4.7 s", "0"],
    ["Qwen 3.8 27B (Groq)", "95 %", "95 %", "100 %", "20 s", "0"],
    ["Nemotron 3 Super 120B (OpenRouter)", "95 %", "95 %", "–", "2.0 s", "0"],
    ["Llama 3 8B (local, offline)", "65 %", "80 %", "100 %", "1.5 s", "0"],
    ["Gemini 3.5 Flash", "–", "–", "–", "–", "64 / 84 (quota)"],
  ];
  s.addTable([[th("Model"), th("Held-out: LLM alone", { align: "center" }), th("Held-out: hybrid", { align: "center" }), th("Dev: hybrid", { align: "center" }), th("Median call", { align: "center" }), th("Provider errors", { align: "center" })],
    ...mc.map((r, i) => r.map((c, j) => td(c, Object.assign({ fill: { color: i === 0 ? H.tealTint : i % 2 ? H.tint : "FFFFFF" }, align: j ? "center" : "left" }, j === 0 || i === 0 ? { bold: i === 0 || j === 0 } : {}))))],
    tableOpts({ x: 0.6, y: 1.75, w: 12.1, colW: [3.9, 1.75, 1.6, 1.4, 1.55, 1.9], rowH: 0.52, fontSize: 14 }));
  const mcNotes = [["FaEquals", "Effectively tied", "Three models miss only “density above 8 g/cm³”, answering with a count of 0."], ["FaTachometerAlt", "Speed and reliability", "Qwen 3.8 is a reasoning model and burns Groq's 8,000 tokens/min; Flash-Lite's errors were free-tier overload."], ["FaBan", "Not scored", "Gemini 3.5 Flash ran out of daily quota, so its score would measure the fallback."]];
  for (let i = 0; i < 3; i++) {
    const x = 0.6 + i * 4.1;
    await hexIcon(s, x, 5.55, 0.6, mcNotes[i][0], i === 2 ? C.accent3 : C.accent1);
    text(s, [B(mcNotes[i][1]), { text: "", options: { breakLine: true } }, { text: mcNotes[i][2], options: { color: C.accent3, fontSize: 13 } }], { x: x + 0.75, y: 5.5, w: 3.15, h: 1.3, fontSize: 15 });
  }
  s.addNotes("Each model planned both question sets on its own, with fallback switched off. The cloud models are effectively tied on accuracy, so we chose the default order by held-out score and by reliability: Flash-Lite first, then GPT-OSS 120B from a different provider.");

  // =============== 18. Answer validation ===============
  s = content("06 · Answer validation", "The answer validator catches invented numbers and false claims", "Results");
  const avt = [["Gemini 3.1 Flash-Lite (default)", "0 of 16", "0", "0", "9.9 s"], ["Llama 3 8B (local)", "2 of 16", "1", "0", "9.3 s"], ["GPT-OSS 120B (Groq)", "2 of 16", "2", "1", "30.2 s"], ["Qwen 3.8 27B (Groq)", "0 of 16", "0", "0", "26.4 s"]];
  s.addTable([[th("Model"), th("Drafts with a problem", { align: "center" }), th("Rewritten", { align: "center" }), th("Still flagged", { align: "center" }), th("Per answer", { align: "center" })],
    ...avt.map((r, i) => r.map((c, j) => td(c, Object.assign({ fill: { color: i === 0 ? H.tealTint : i % 2 ? H.tint : "FFFFFF" }, align: j ? "center" : "left" }, j === 0 ? { bold: true } : {}))))],
    tableOpts({ x: 0.6, y: 1.75, w: 7.6, colW: [3.0, 1.4, 1.0, 1.1, 1.1], rowH: 0.7, fontSize: 14 }));
  text(s, "16 full answers per model. Qwen 3.8: 7 answer calls hit Groq limits, so a template answer with the verified table was shown.", { x: 0.6, y: 5.45, w: 7.6, h: 0.7, fontSize: 13, color: C.accent3, italic: true });
  const caught = [["Llama 3 8B", "invented two densities and a “90 %”; garbled OFEUN06 → OFERUN06, corrected automatically"], ["GPT-OSS 120B", "claimed two MOFs were on “Pareto front 1”; NSGA-II ranked them on front 2 → shown with a warning"]];
  text(s, "What it caught", { x: 8.7, y: 1.75, w: 4.0, h: 0.45, fontSize: 18, bold: true, fontFace: "Cambria" });
  for (let i = 0; i < 2; i++) {
    const y = 2.35 + i * 2.2;
    card(s, 8.7, y, 4.0, 2.0, H.copTint);
    s.addImage({ data: await icon("FaExclamationTriangle", H.copper), x: 8.95, y: y + 0.22, w: 0.35, h: 0.35 });
    text(s, caught[i][0], { x: 9.45, y: y + 0.2, w: 3.1, h: 0.4, fontSize: 16, bold: true });
    text(s, caught[i][1], { x: 8.95, y: y + 0.7, w: 3.55, h: 1.2, fontSize: 14, color: C.text2 });
  }
  s.addNotes("Every first draft is checked. The default model needed no corrections. The local model invented numbers once and garbled an ID, which was fixed automatically. GPT-OSS 120B made a false Pareto-front claim that a plain number check would have missed; the claim checker flagged it.");

  // =============== 19. Property prediction ===============
  s = content("06 · Surrogates", "XGBoost: surface-area R² = 0.982 with calibrated intervals", "Results");
  [["0.982", "R² surface area (XGBoost)", C.accent1], ["90 m²/g", "mean absolute error", C.accent1], ["90.5 %", "test coverage of the 90 % conformal interval", C.accent2], ["0.828", "R² void fraction (XGBoost)", C.accent1]].forEach(([n, l, c], i) => stat(s, 0.6 + i * 3.1, 1.6, 2.9, n, l, c, 34));
  s.addChart(pres.charts.BAR, [
    { name: "Surface area", labels: ["Mean baseline", "Ridge", "Gaussian process", "XGBoost", "FT-Transformer"], values: [0.343, 0.947, 0.977, 0.982, 0.981] },
    { name: "Void fraction", labels: ["Mean baseline", "Ridge", "Gaussian process", "XGBoost", "FT-Transformer"], values: [0, 0.780, 0.796, 0.828, 0.823] },
  ], {
    x: 0.5, y: 3.15, w: 6.3, h: 3.7, barDir: "bar", barGapWidthPct: 50, chartColors: [H.teal, H.grey],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 10, dataLabelColor: H.navy, dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "0.000",
    showLegend: true, legendPos: "b", legendFontSize: 11, legendFontFace: "+mn-lt", legendColor: H.slate,
    showTitle: true, title: "Test R² (held-out 10 %)", titleFontSize: 13, titleFontFace: "+mn-lt", titleColor: H.navy,
    valAxisMaxVal: 1.15, valAxisMinVal: 0, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, catAxisOrientation: "maxMin",
    catAxisLabelColor: H.slate, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt",
  });
  s.addImage({ path: path.join(__dirname, "parity_xgb_ft.png"), x: 7.0, y: 3.3, w: 5.7, h: 2.85, altText: "Parity plots, XGBoost and FT-Transformer, surface area" });
  text(s, "Predicted vs actual surface area on test MOFs. XGBoost trains 400× faster than the FT-Transformer (0.25 s vs 112 s) for the same accuracy.", { x: 7.0, y: 6.2, w: 5.7, h: 0.6, fontSize: 12, color: C.accent3, italic: true });
  s.addNotes("XGBoost is the production model: R squared 0.982, mean error 90 m2/g. The FT-Transformer ties it, which matches Grinsztajn et al.: on medium-sized tabular data, trees are as good and much faster. The conformal interval covers 90.5% of test MOFs, close to the promised 90%.");

  // =============== 20. SHAP + similarity ===============
  s = content("06 · Explanations", "SHAP drivers are physically sensible; embeddings find similar MOFs", "Results");
  s.addImage({ path: PROJ + "/artifacts/property_models/shap_summary_Surface_Area.png", x: 0.5, y: 1.7, w: 6.4, h: 3.66, altText: "SHAP summary for the surface-area surrogate" });
  text(s, "Pore volume and void fraction dominate surface area; density dominates void fraction.", { x: 0.6, y: 5.55, w: 6.2, h: 0.7, fontSize: 15 });
  text(s, "Similarity search: 1,000 queries × 10 neighbours", { x: 7.3, y: 1.75, w: 5.4, h: 0.45, fontSize: 16, bold: true, fontFace: "Cambria" });
  s.addTable([[th("Neighbours from"), th("Descriptor gap (σ)", { align: "center" }), th("Same metal", { align: "center" })],
    [td("FT-Transformer embedding", { bold: true, fill: { color: H.tealTint } }), td("0.077", { align: "center", fill: { color: H.tealTint } }), td("27.8 %", { align: "center", bold: true, fill: { color: H.tealTint } })],
    [td("k-NN on raw descriptors"), td("0.068", { align: "center" }), td("22.8 %", { align: "center" })],
    [td("Random MOFs", { fill: { color: H.tint } }), td("0.952", { align: "center", fill: { color: H.tint } }), td("8.0 %", { align: "center", fill: { color: H.tint } })]],
    tableOpts({ x: 7.3, y: 2.35, w: 5.4, colW: [2.5, 1.6, 1.3], rowH: 0.52, fontSize: 14 }));
  card(s, 7.3, 4.65, 5.4, 1.65);
  text(s, "Nearly as close as k-NN on the numbers (k-NN is the upper bound on that metric), but more often the same metal, because metal and open-metal-site are input tokens. 62 % overlap with k-NN lists.", { x: 7.5, y: 4.75, w: 5.0, h: 1.45, fontSize: 14, color: C.text2, valign: "middle" });
  s.addNotes("SHAP shows which descriptors drive each prediction; the ranking is physically sensible. For similarity, the FT-Transformer neighbours are almost as close as raw k-NN on the descriptors, but share the query's metal more often, which is what a chemist expects from 'similar'.");

  // =============== 21. Limitations addressed ===============
  s = content("06 · Against the base paper", "Seven of ChatMOF's nine limitations are fully addressed", "Results");
  const lv = [
    ["No intrinsic materials knowledge", "RAG over curated notes + ChatMOF paper", "Done"],
    ["Token-context limits", "SQL filters first; LLM sees ≤ 10 rows", "Done"],
    ["Logic errors in LLM code", "JSON plan, validator, whitelisted SQL", "Done"],
    ["Restricted search space", "all 12,020 MOFs searched and ranked", "Done"],
    ["Narrow topology coverage", "all CoRE-MOF structures, 65 metals", "Done*"],
    ["A pretrained model per property", "surrogates trained on the table", "Done*"],
    ["General, non-fine-tuned LLM", "domain prompts, few-shot, presets", "Partly"],
    ["High compute cost", "ms screening; XGBoost trains in 0.25 s", "Done"],
    ["Unvalidated output", "answer validator, intervals, SHAP, benchmark", "Done"],
  ];
  s.addTable([[th("ChatMOF limitation"), th("What MOFChat does"), th("Status", { align: "center" })],
    ...lv.map((r, i) => r.map((c, j) => td(c, Object.assign({ fill: { color: i % 2 ? H.tint : "FFFFFF" } }, j === 2 ? { align: "center", bold: true, color: c === "Partly" ? H.copper : H.teal } : j === 0 ? { bold: true } : {}))))],
    tableOpts({ x: 0.6, y: 1.7, w: 12.1, colW: [3.9, 6.6, 1.6], rowH: 0.45, fontSize: 14 }));
  text(s, "* for recommendation and for properties in the table: no structure generation, no gas uptake without uptake labels", { x: 0.6, y: 6.45, w: 12, h: 0.35, fontSize: 12, color: C.accent3, italic: true });
  s.addNotes("This maps each limitation from the base paper to what we built. Be upfront about the two asterisks: we recommend existing MOFs rather than generating new ones, and we cannot predict gas uptake because the table has no uptake labels. The LLM is not fine-tuned, so that one is partial.");

  // =============== 22. App ===============
  pres.addSection({ title: "Application" });
  s = content("07 · Application", "The app shows the answer, the verified table and how it was made", "Application");
  const shot = (p, x, y, w, h, cap) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x - 0.06, y: y - 0.06, w: w + 0.12, h: h + 0.12, rectRadius: 0.06, fill: { color: "FFFFFF" }, line: { color: "D5DEE2", width: 0.75 }, shadow: { type: "outer", color: "0F2433", opacity: 0.18, blur: 8, offset: 2, angle: 90 } });
    s.addImage({ path: p, x, y, w, h, altText: cap });
    text(s, cap, { x, y: y + h + 0.14, w, h: 0.35, fontSize: 13, color: C.accent3, italic: true });
  };
  shot(path.join(__dirname, "shot_answer.png"), 0.7, 1.8, 5.84, 2.8, "“Which zinc MOFs have high surface area and low density?”");
  shot(path.join(__dirname, "shot_pareto.png"), 6.8, 1.8, 5.9, 2.8, "The same answer's NSGA-II Pareto plot: recommended set in copper");
  text(s, "Every answer also shows the plan, the SQL, the validator report and which model answered. With no language model at all, the rule planner and template answers still work.", { x: 0.7, y: 5.3, w: 12.0, h: 0.6, fontSize: 15, color: C.text2 });
  const pages = [["FaComments", "Chat"], ["FaSlidersH", "Explore & optimise"], ["FaChartBar", "Predict & explain"], ["FaClipboardCheck", "Evaluation"]];
  for (let i = 0; i < pages.length; i++) {
    const x = 0.7 + i * 3.05;
    await hexIcon(s, x, 6.1, 0.55, pages[i][0], i % 2 ? C.accent2 : C.accent1);
    text(s, pages[i][1], { x: x + 0.7, y: 6.12, w: 2.3, h: 0.45, fontSize: 15, bold: true, valign: "middle" });
  }
  s.addNotes("Live demo order (docs/VIVA_GUIDE.md): 1) 'Find me 3 MOFs with surface area greater than 4000 and void fraction greater than 0.8', open 'How this answer was produced'. 2) 'Which zinc MOFs have high surface area and low density?', open the Pareto plot. 3) 'Recommend MOFs for CO2 capture', show sources and caveats. 4) 'MOFs with surface area above 20000', it says none exist and shows the closest. 5) A prediction question, show the interval and SHAP. The app also works with no language model at all.");

  // =============== 23. Lessons ===============
  pres.addSection({ title: "Conclusion" });
  s = content("08 · Discussion", "Four lessons from building and testing MOFChat", "Conclusion");
  const lessons = [
    ["FaSearchMinus", "Similarity ≠ constraints", "A two-tower model needs paired training data, and numeric filters belong in a database. This is why review 1 scored 9.4 %."],
    ["FaCodeBranch", "LLMs and rules complement", "Rules are exact but brittle on new phrasings; LLMs generalise but make schema errors. Validation and the hybrid merge combine both."],
    ["FaBug", "Use the app, not only the benchmark", "The benchmark scores plans, not text. Using the app found four bugs (false ≥ 6000 claim, overridden presets, “90 %” false positive, “8 318”). Each now has a unit test."],
    ["FaTree", "Trees still win on small tables", "On ~8,000 MOFs with 6 features XGBoost ties the FT-Transformer, trains 400× faster and gives exact SHAP."],
  ];
  for (let i = 0; i < 4; i++) {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.6 + col * 6.15, y = 1.75 + row * 2.5;
    card(s, x, y, 5.95, 2.3);
    await hexIcon(s, x + 0.3, y + 0.3, 0.7, lessons[i][0], i === 2 ? C.accent2 : C.accent1);
    text(s, lessons[i][1], { x: x + 1.2, y: y + 0.38, w: 4.55, h: 0.45, fontSize: 18, bold: true, fontFace: "Cambria" });
    text(s, lessons[i][2], { x: x + 1.2, y: y + 0.9, w: 4.55, h: 1.3, fontSize: 14, color: C.text2 });
  }
  s.addNotes("If asked what we learned: these four. The third is worth emphasising: our benchmark was at 100%, yet using the finished app with GPT-OSS 20B exposed four real bugs in the written answers. Each was fixed, given a unit test built from the real output, and the evaluation was re-run.");

  // =============== 24. Limitations & future ===============
  s = content("08 · Limitations", "What MOFChat does not do yet, and what comes next", "Conclusion");
  const lf = [
    ["No gas-uptake labels", "Attach GCMC uptake data; reuse the surrogate pipeline"],
    ["No structure generation", "Recommend only; a generator (e.g. genetic algorithm) is future work"],
    ["Offline model at 80 %", "LoRA fine-tuning of Llama 3 on plan examples"],
    ["Free-text reasoning unchecked", "Validator covers IDs, numbers and claims; sources are shown"],
    ["Presets are heuristics", "Replace with learned rules once uptake data exists"],
    ["Descriptor-only similarity", "Add structure embeddings (e.g. MOFTransformer)"],
  ];
  text(s, "LIMITATION", { x: 1.45, y: 1.7, w: 4.5, h: 0.35, fontSize: 13, bold: true, color: C.accent2, charSpacing: 2 });
  text(s, "NEXT STEP", { x: 6.9, y: 1.7, w: 5.5, h: 0.35, fontSize: 13, bold: true, color: C.accent1, charSpacing: 2 });
  lf.forEach(([l, f], i) => {
    const y = 2.2 + i * 0.75;
    hexNum(s, 0.6, y, 0.55, String(i + 1), C.accent2, C.background1, 13);
    text(s, l, { x: 1.45, y, w: 4.6, h: 0.5, fontSize: 16, bold: true, valign: "middle" });
    arrow(s, 6.15, y + 0.25, 6.65, y + 0.25, H.slate);
    text(s, f, { x: 6.9, y, w: 5.8, h: 0.5, fontSize: 15, color: C.text2, valign: "middle" });
  });
  s.addNotes("Be honest about scope. The biggest gap is gas uptake: the table has geometry only. The hMOF folder already has structures and energy grids, so attaching uptake labels would let the same pipeline predict adsorption directly.");

  // =============== 25. Conclusion ===============
  s = pres.addSlide({ masterName: "MOF_DARK", sectionTitle: "Conclusion" });
  text(s, "CONCLUSION", { x: 0.7, y: 0.6, w: 6, h: 0.35, fontSize: 13, bold: true, color: C.accent5, charSpacing: 2 });
  text(s, "MOFChat turns the ChatMOF idea into a validated, measurable system that runs on free models or fully offline", { x: 0.7, y: 1.05, w: 11.9, h: 1.3, fontSize: 28, bold: true, color: C.background1, fontFace: "Cambria" });
  const fin = [["100 %", "held-out exact answers, default model (review 1: 5 %)"], ["80 %", "fully offline with Llama 3 8B, +15 pts from validation"], ["0.982", "surface-area R², 90.5 % interval coverage"], ["14", "free or local LLMs with automatic fallback"]];
  fin.forEach(([n, l], i) => {
    const x = 0.7 + i * 3.05;
    text(s, n, { x, y: 2.9, w: 2.85, h: 0.9, fontSize: 44, bold: true, color: i % 2 ? C.accent6 : C.accent5, fontFace: "Cambria", valign: "bottom" });
    text(s, l, { x, y: 3.9, w: 2.7, h: 0.9, fontSize: 14, color: "C9D9E0" });
  });
  text(s, "Exact answers over all 12,020 MOFs  ·  NSGA-II multi-objective ranking  ·  calibrated, explained predictions  ·  literature grounding  ·  an answer validator that keeps the LLM honest", { x: 0.7, y: 5.35, w: 11.9, h: 0.9, fontSize: 16, color: C.background1 });
  text(s, "Every number in this deck is produced by evaluate.py and recorded in docs/RESULTS.md.", { x: 0.7, y: 6.45, w: 11.9, h: 0.4, fontSize: 13, color: "9FB6C1", italic: true });
  s.addNotes("Close with the four numbers, then the one-line summary: we kept ChatMOF's convenience and added the checks that make its answers trustworthy.");

  // =============== 26. References ===============
  s = content("References", "References", "Conclusion");
  const refs = [
    "Y. Kang, J. Kim, “ChatMOF: an artificial intelligence system for predicting and generating metal-organic frameworks using large language models,” Nat. Commun., 15, 4705, 2024.",
    "Y. Kang, H. Park, B. Smit, J. Kim, “A multi-modal pre-training transformer for universal transfer learning in metal–organic frameworks,” Nat. Mach. Intell., 5, 309–318, 2023.",
    "Y. G. Chung et al., “Advances, updates, and analytics for the computation-ready, experimental metal–organic framework database: CoRE MOF 2019,” J. Chem. Eng. Data, 64, 5985–5998, 2019.",
    "Y. Gorishniy, I. Rubachev, V. Khrulkov, A. Babenko, “Revisiting deep learning models for tabular data,” NeurIPS, 2021.",
    "L. Grinsztajn, E. Oyallon, G. Varoquaux, “Why do tree-based models still outperform deep learning on typical tabular data?” NeurIPS Datasets & Benchmarks, 2022.",
    "P. Lewis et al., “Retrieval-augmented generation for knowledge-intensive NLP tasks,” NeurIPS, 2020.",
    "S.-A. Chen et al., “TableRAG: Million-token table understanding with language models,” NeurIPS, 2024.",
    "Z. Wang et al., “Chain-of-Table: Evolving tables in the reasoning chain for table understanding,” ICLR, 2024.",
    "K. Deb, A. Pratap, S. Agarwal, T. Meyarivan, “A fast and elitist multiobjective genetic algorithm: NSGA-II,” IEEE Trans. Evol. Comput., 6, 182–197, 2002.",
    "S. M. Lundberg, S.-I. Lee, “A unified approach to interpreting model predictions,” NeurIPS, 2017.",
    "Z. Zheng, O. Zhang, C. Borgs, J. T. Chayes, O. M. Yaghi, “ChatGPT chemistry assistant for text mining and the prediction of MOF synthesis,” J. Am. Chem. Soc., 145, 18048–18062, 2023.",
    "T. M. Pruyn et al., “MOF-ChemUnity: Literature-informed large language models for metal–organic framework research,” J. Am. Chem. Soc., 2025.",
  ];
  const half = 6;
  [refs.slice(0, half), refs.slice(half)].forEach((col, c) => {
    text(s, col.map((r, i) => ({ text: `[${c * half + i + 1}]  ${r}`, options: { breakLine: i < col.length - 1, paraSpaceAfter: 7 } })), { x: 0.6 + c * 6.15, y: 1.65, w: 5.95, h: 5.2, fontSize: 12, color: C.text2 });
  });
  s.addNotes("Twelve of the fifteen verified references; the full annotated list is docs/LITERATURE_REVIEW.md.");

  // =============== 27. Thank you ===============
  s = pres.addSlide({ masterName: "MOF_DARK", sectionTitle: "Conclusion" });
  lattice(s, 8.3, 1.0, 5, 6, 1.0, new Set(["0,0", "2,3", "4,5", "3,1"]));
  text(s, "Thank you", { x: 0.7, y: 2.0, w: 7.2, h: 1.2, fontSize: 60, bold: true, color: C.background1, fontFace: "Cambria" });
  text(s, "Questions and live demo", { x: 0.7, y: 3.25, w: 7.2, h: 0.6, fontSize: 24, color: C.accent6 });
  text(s, [{ text: "Code  ", options: { bold: true, color: C.accent5 } }, { text: "github.com/Sai-Mohith24/MOFChat-AI-Driven-Material-Recommendation-", options: { color: "D6E4EA" } }], { x: 0.7, y: 4.6, w: 7.3, h: 0.7, fontSize: 14 });
  text(s, "Team 09  ·  22AIE452 Data Driven Material Modeling and Simulation", { x: 0.7, y: 5.5, w: 7.3, h: 0.4, fontSize: 14, color: "9FB6C1" });
  s.addNotes("Open the app for the demo questions on the application slide, or take questions. docs/VIVA_GUIDE.md lists likely questions and answers.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
}
build().catch((e) => { console.error(e); process.exit(1); });

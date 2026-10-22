// MOFChat final-review deck in the style of the review-1 template (A4 landscape, Amrita logo,
// blue heading bars, Arial). One text size (FS) for all body text, tables, diagrams and charts.
// Numbers are read from the project's result files at build time.
// Run from this folder:  NODE_PATH=<node_modules> PPTX_SKILL=<pptx skill dir> node build.js [out.pptx]
const pptxgen = require("pptxgenjs");
const sharp = require("sharp");
const fs = require("fs");
const path = require("path");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const HERE = __dirname;
const PROJ = path.resolve(HERE, "../../..");
const OUT = process.argv[2] || path.join(HERE, "..", "MOFChat_Final_Review.pptx");
const J = (p) => JSON.parse(fs.readFileSync(path.join(PROJ, p)));
const DL = J("artifacts/dl_eval/metrics.json");
const PM = J("artifacts/property_models/metrics.json");
const SUM = J("artifacts/eval/summary.json");
const FTM = J("artifacts/ft_embeddings/metrics.json");
const fig = (n) => path.join(PROJ, "artifacts/dl_eval", n);

const FS = 12;          // the one body text size
const TITLE_FS = 24;    // slide titles in the heading bar

// Office 2007 theme of the review-1 template
const THEME = {
  name: "MOFChat Review Template", headFontFace: "Arial", bodyFontFace: "Arial",
  colors: { dk1: "000000", lt1: "FFFFFF", dk2: "1F497D", lt2: "EEECE1", accent1: "4F81BD", accent2: "C0504D",
    accent3: "9BBB59", accent4: "8064A2", accent5: "4BACC6", accent6: "F79646", hlink: "0000FF", folHlink: "800080" },
};
const H = { bar: "B8CCE4", navy: "1F497D", blue: "4F81BD", red: "C00000", band: "DBE5F1", grey: "595959", line: "95B3D7",
  pale: { purple: "E4DFEC", green: "EBF1DE", aqua: "DAEEF3", pink: "F2DCDB", grey: "F2F2F2", peach: "FDE9D9", blue: "DCE6F2", yellow: "FFF2CC" } };

const pres = new pptxgen();
pres.defineLayout({ name: "A4L", width: 11.69, height: 8.27 });
pres.layout = "A4L";
pres.theme = { headFontFace: "Arial", bodyFontFace: "Arial" };
pres.title = "MOFChat - Final Review";
pres.author = "Team 09, 22AIE452";
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: "TEMPLATE_CONTENT",
  background: { color: "FFFFFF" },
  objects: [
    { rect: { x: 0.25, y: 0.22, w: 11.19, h: 0.62, fill: { color: H.bar }, line: { color: H.bar, width: 0 } } },
    { placeholder: { options: { name: "title", type: "title", x: 0.4, y: 0.22, w: 10.9, h: 0.62, fontSize: TITLE_FS, bold: true,
      color: C.text1, fontFace: "Arial", valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 10.85, y: 7.9, w: 0.55, h: 0.25, fontSize: 9, color: "7F7F7F", align: "right" },
});
pres.defineSlideMaster({ title: "TEMPLATE_BLANK", background: { color: "FFFFFF" }, objects: [] });

// ---------------------------------------------------------------- helpers
const T = (s, t, o) => s.addText(t, Object.assign({ isTextBox: true, margin: 0, fontFace: "Arial", color: C.text1, fontSize: FS, valign: "top" }, o));
const B = (t, o = {}) => ({ text: t, options: Object.assign({ bold: true }, o) });
const R = (t, o = {}) => ({ text: t, options: o });
function slide(title, section) {
  const s = pres.addSlide({ masterName: "TEMPLATE_CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  return s;
}
function bullets(s, items, o) {
  const runs = items.map((it, i) => {
    const arr = Array.isArray(it) ? it : [it];
    return arr.map((r, j) => {
      const isObj = typeof r === "object";
      const opts = Object.assign({}, isObj ? r.options : {});
      if (j === 0) Object.assign(opts, { bullet: { indent: 14 }, paraSpaceAfter: 5 });
      if (j === arr.length - 1 && i < items.length - 1) opts.breakLine = true;
      return { text: isObj ? r.text : r, options: opts };
    });
  }).flat();
  T(s, runs, o);
}
function sub(s, t, x, y, w, color = H.red) { T(s, t, { x, y, w, h: 0.3, bold: true, color }); }
function caption(s, t, x, y, w, align = "center") { T(s, t, { x, y, w, h: 0.3, italic: true, color: H.grey, align }); }
async function img(s, p, x, y, w, maxH) {
  const m = await sharp(p).metadata();
  let h = w * m.height / m.width;
  if (maxH && h > maxH) { w = maxH * m.width / m.height; h = maxH; }
  s.addImage({ path: p, x, y, w, h, altText: path.basename(p) });
  return { w, h };
}
function box(s, x, y, w, h, text, fill, o = {}) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill },
    line: { color: o.border || "404040", width: 1 }, shadow: { type: "outer", color: "000000", opacity: 0.25, blur: 3, offset: 2, angle: 45 } });
  T(s, text, { x: x + 0.05, y, w: w - 0.1, h, align: "center", valign: "middle", bold: o.bold !== false, color: o.color || "000000" });
}
function arrow(s, x1, y1, x2, y2, color = "262626", width = 2) {
  s.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    flipH: x2 < x1, flipV: y2 < y1, line: { color, width, endArrowType: "triangle" } });
}
function line(s, x1, y1, x2, y2, color = "262626", width = 2, dash) {
  s.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    flipH: x2 < x1, flipV: y2 < y1, line: { color, width, dashType: dash } });
}
const th = (t, o = {}) => ({ text: t, options: Object.assign({ bold: true, color: "FFFFFF", fill: { color: H.blue } }, o) });
const bold = (t, o = {}) => ({ text: t, options: Object.assign({ bold: true }, o) });
function table(s, header, rows, o) {
  const body = rows.map((r, i) => r.map((c) => {
    const cell = typeof c === "object" ? c : { text: String(c), options: {} };
    cell.options = Object.assign({ fill: { color: i % 2 ? "FFFFFF" : H.band } }, cell.options);
    return cell;
  }));
  s.addTable([header.map((h) => (typeof h === "object" ? h : th(h))), ...body],
    Object.assign({ fontFace: "Arial", fontSize: FS, color: "000000", border: { type: "solid", pt: 0.75, color: H.line },
      margin: [2, 5, 2, 5], valign: "middle" }, o));
}
const CHART = { titleFontSize: FS, titleFontFace: "Arial", legendFontSize: FS, legendFontFace: "Arial", catAxisLabelFontSize: FS,
  catAxisLabelFontFace: "Arial", valAxisLabelFontSize: FS, valAxisLabelFontFace: "Arial", dataLabelFontSize: FS, dataLabelFontFace: "Arial",
  catAxisTitleFontSize: FS, valAxisTitleFontSize: FS, catAxisTitleFontFace: "Arial", valAxisTitleFontFace: "Arial" };
const pct = (v, d = 1) => (100 * v).toFixed(d) + " %";
const f3 = (v) => Number(v).toFixed(3);

async function build() {
  // ===================================================== Title
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "TEMPLATE_BLANK", sectionTitle: "Introduction" });
  await img(s, path.join(HERE, "amrita_logo.png"), 3.16, 0.9, 5.4);
  s.addShape(pres.shapes.RECTANGLE, { x: 1.3, y: 2.65, w: 9.1, h: 1.55, fill: { color: "E6B9B8" }, line: { color: "E6B9B8", width: 0 } });
  T(s, "MOFChat: Explainable, Data-Grounded MOF Recommendation with Validated LLM Planning, Multi-Objective Optimisation and Deep-Learning Surrogates",
    { x: 1.5, y: 2.65, w: 8.7, h: 1.55, fontSize: 21, fontFace: "Arial Black", align: "center", valign: "middle" });
  T(s, "22AIE452 - Data Driven Material Modeling and Simulation  |  Final Review", { x: 1.3, y: 4.4, w: 9.1, h: 0.3, color: "808080", align: "center" });
  T(s, "Team_09", { x: 1.3, y: 4.95, w: 9.1, h: 0.3, bold: true, align: "center" });
  const team = ["Amrutha T - 24255", "Charan Tej Reddy Y - 24259", "Poojitha D - 24263", "Enku Sai Mohith - 24316", "Ramu Jahna Bindu - 24249"];
  T(s, team.map((t, i) => R(t, { breakLine: i < team.length - 1 })), { x: 3.85, y: 5.35, w: 4.0, h: 1.6, align: "center", paraSpaceAfter: 4 });

  // ===================================================== Outline
  s = slide("Outline", "Introduction");
  const outline = [["Introduction", "MOFs, problem statement, base paper (ChatMOF)"], ["Objectives and Novelty", "What we set out to do and how we improve on ChatMOF"],
    ["Literature Review", "18 papers from 2024 to 2026 and the research gap"], ["Dataset and Feature Extraction", "CoRE MOF 2019, preprocessing, descriptor and embedding analysis"],
    ["Pipeline and Architecture", "Dashboard-to-backend pipeline, models used, FT-Transformer architecture"],
    ["Results", "Retrieval benchmark, classification (accuracy, ROC, confusion matrices), regression, learning curves"],
    ["Application, Conclusion and Future Work", "Streamlit application, limitations, references"]];
  outline.forEach(([h, d], i) => {
    const y = 1.25 + i * 0.88;
    s.addShape(pres.shapes.OVAL, { x: 0.8, y, w: 0.5, h: 0.5, fill: { color: H.blue }, line: { color: H.blue, width: 0 } });
    T(s, String(i + 1), { x: 0.8, y, w: 0.5, h: 0.5, align: "center", valign: "middle", bold: true, color: "FFFFFF" });
    T(s, [B(h, { color: H.navy, breakLine: true }), R(d, { color: H.grey })], { x: 1.55, y: y - 0.02, w: 9, h: 0.6 });
  });

  // ===================================================== Introduction
  s = slide("Introduction", "Introduction");
  T(s, [R("Metal-Organic Frameworks (MOFs) are crystalline porous materials made by linking metal ions with organic molecules, creating microscopic cages. Their tunable pores make them candidates for "),
    B("carbon capture, hydrogen and methane storage, gas separation and catalysis"), R(".")], { x: 0.4, y: 1.1, w: 7.0, h: 0.9 });
  T(s, [R("Selecting the right MOF is difficult: the CoRE-MOF database alone has "), B("12,020 MOFs"), R(", and a good choice has to balance several properties (surface area, pore size, density, metal sites) and needs domain knowledge.")],
    { x: 0.4, y: 2.1, w: 7.0, h: 0.9 });
  sub(s, "Problem statement", 0.4, 3.2, 7);
  T(s, "Existing LLM agents such as ChatMOF make MOF search conversational, but they generate code that can fail, depend on paid models, run into token limits and return numbers that are never checked against the data.",
    { x: 0.4, y: 3.55, w: 7.0, h: 0.9 });
  sub(s, "Aim", 0.4, 4.65, 7);
  T(s, "A conversational assistant that answers MOF questions exactly from the full database, ranks trade-offs between properties, predicts properties with uncertainty and explanations, runs on free or offline models, and verifies its own answers.",
    { x: 0.4, y: 5.0, w: 7.0, h: 0.9 });
  await img(s, path.join(HERE, "mof_structure.jpg"), 8.0, 1.2, 3.0);
  caption(s, "MOF framework: metal nodes joined by organic linkers", 7.6, 4.5, 3.8);
  table(s, ["Dataset at a glance", "Value"], [["MOFs in CoRE MOF 2019", "12,020"], ["Different metals", "65"], ["MOFs with zero accessible surface area", "27 %"]],
    { x: 7.6, y: 5.05, w: 3.8, colW: [2.8, 1.0], rowH: 0.36 });

  // ===================================================== Base paper
  s = slide("Base Paper: ChatMOF (Kang and Kim, 2024)", "Introduction");
  sub(s, "What the base paper did", 0.4, 1.05, 5.4);
  bullets(s, ["GPT-4 agent that plans tool calls (ReAct)", "Search: the LLM writes pandas code over the CoRE-MOF table", "Prediction: MOFTransformer (one fine-tuned model per property)",
    "Generation: genetic algorithm with PORMAKE"], { x: 0.4, y: 1.4, w: 5.4, h: 1.5 });
  table(s, ["Task", "Reported accuracy"], [["Search", "96.9 %"], ["Prediction", "95.7 %"], ["Generation", "87.5 %"]], { x: 0.4, y: 3.1, w: 3.6, colW: [1.8, 1.8], rowH: 0.36 });
  T(s, "https://www.nature.com/articles/s41467-024-48998-4", { x: 0.4, y: 4.75, w: 5.4, h: 0.3, color: "0000FF", underline: true,
    hyperlink: { url: "https://www.nature.com/articles/s41467-024-48998-4" } });
  sub(s, "Drawbacks reported in the base paper", 6.1, 1.05, 5.3);
  const lims = ["No intrinsic materials knowledge (the LLM only plans tools)", "Token-context limits: 4 % of search tasks failed", "Reasoning and logic errors in generated code",
    "Restricted search space (about 100 parent structures)", "Narrow topology coverage (9 topologies)", "One pretrained model needed per property",
    "General, non-fine-tuned LLM (GPT-4)", "High compute cost (GA and simulations)", "Results are not validated against the data"];
  lims.forEach((t, i) => T(s, [B(`L${i + 1}  `, { color: H.red }), R(t)], { x: 6.1, y: 1.45 + i * 0.55, w: 5.3, h: 0.5 }));

  // ===================================================== Objectives & novelty
  pres.addSection({ title: "Objectives" });
  s = slide("Objectives and Our Novelty", "Objectives");
  sub(s, "Objectives", 0.4, 1.05, 4.2);
  const objs = ["Exact answers over all 12,020 MOFs using free or local LLMs", "Safe LLM planning with validation, self-correction and fallback", "Multi-objective ranking with NSGA-II",
    "Deep-learning and ML surrogate models with uncertainty and SHAP", "Knowledge grounding by retrieval (RAG)", "Measured results: benchmark, held-out set, classification and regression metrics"];
  objs.forEach((t, i) => T(s, [B(`${i + 1}. `, { color: H.navy }), R(t)], { x: 0.4, y: 1.45 + i * 0.75, w: 4.2, h: 0.7 }));
  table(s, ["Base-paper limitation", "MOFChat novelty"], [
    ["No materials knowledge", "RAG over curated notes and the ChatMOF paper"], ["Token limits", "SQL filters first; the LLM sees at most 10 verified rows"],
    ["Logic errors in code", "The LLM writes a JSON plan; a validator checks and repairs it"], ["Small search space", "All 12,020 MOFs searched and ranked (NSGA-II)"],
    ["Only 9 topologies", "Every CoRE-MOF structure, 65 metals"], ["One model per property", "Our own XGBoost and FT-Transformer surrogates"],
    ["Proprietary GPT-4", "14 free or local LLMs with automatic fallback"], ["High computation", "Millisecond surrogate models instead of simulations"],
    ["No validation", "Answer validator, conformal intervals, SHAP and a benchmark"]],
  { x: 4.85, y: 1.1, w: 6.55, colW: [2.3, 4.25], rowH: 0.55 });

  // ===================================================== Literature (4 slides)
  pres.addSection({ title: "Literature" });
  const LIT = [
    ["ChatMOF: an AI system for predicting and generating MOFs using LLMs", "Kang, Kim", "2024, Nat. Commun.", "GPT-4 agent writes pandas code; MOFTransformer; genetic algorithm", "96.9 / 95.7 / 87.5 % on search / prediction / generation", "Token limits, code errors, answers not checked", "Base paper; we use validated JSON plans and SQL"],
    ["Augmenting LLMs with chemistry tools (ChemCrow)", "Bran et al.", "2024, Nat. Mach. Intell.", "GPT-4 with 18 expert tools in a reason-act loop", "Planned real syntheses; found a new chromophore", "Needs GPT-4; tool outputs not cross-checked", "Tool calling; our tools are deterministic and tested"],
    ["MOFDiff: coarse-grained diffusion for MOF design", "Fu, Xie, Rosen et al.", "2024, ICLR", "Equivariant diffusion over building blocks", "Valid, novel MOFs for CO2 capture", "Needs simulation to validate", "Generation is future work"],
    ["TableRAG: million-token table understanding", "Chen et al.", "2024, NeurIPS", "Schema and cell retrieval before the LLM", "Table QA on very large tables", "Numeric filters still judged by the LLM", "We filter with SQL first"],
    ["Chain-of-Table: evolving tables in the reasoning chain", "Wang et al.", "2024, ICLR", "LLM plans table operations step by step", "Best results on WikiTQ and TabFact", "No domain validation of operations", "We validate every planned operation"],
    ["Detecting hallucinations in LLMs using semantic entropy", "Farquhar, Kossen, Kuhn, Gal", "2024, Nature", "Entropy over the meanings of sampled answers", "Detects confabulations without task data", "Misses consistent errors; needs many samples", "We check answers against the data instead"],
    ["Harnessing LLMs to collect and analyze MOF property data (L2M3)", "Lee, Kang, Bae, Kim", "2025, JACS", "LLM text mining of over 40,000 articles", "Experimental MOF database and synthesis recommender", "Extraction errors from text", "Source of real labels for future uptake models"],
    ["MOF-ChemUnity: literature-informed LLMs for MOF research", "Pruyn et al.", "2025, JACS", "Multi-agent LLM links literature names to CSD structures", "Literature-grounded answers via a knowledge graph", "Large infrastructure", "Our RAG grounds answers in notes and papers"],
    ["Accurate predictions on small data with a tabular foundation model (TabPFN)", "Hollmann et al.", "2025, Nature", "Transformer pretrained on synthetic tables", "Beats tuned GBDT on small tables", "About 10k rows / 500 features at most", "Possible surrogate for our 8k-row tables"],
    ["TabM: tabular deep learning with parameter-efficient ensembling", "Gorishniy, Kotelnikov, Babenko", "2025, ICLR", "MLP with BatchEnsemble", "Beats attention-based tabular models", "Generic benchmarks only", "Matches our finding: DL close to trees"],
    ["LLaMP: LLM for high-fidelity materials knowledge retrieval", "Chiang et al.", "2025, EMNLP", "Hierarchical ReAct agents over Materials Project", "Grounded answers with a confidence metric", "Needs the Materials Project API", "Same grounding idea with a local MOF database"],
    ["System of agentic AI for the discovery of MOFs (MOFGen)", "Inizan et al.", "2025, arXiv", "LLM proposes compositions; diffusion and quantum-chemistry agents", "Synthesizable MOF candidates", "Heavy compute; preprint", "We verify answers against the database"],
    ["L2M3OF: a large language multimodal model for MOFs", "Cui et al.", "2025, arXiv", "Crystal encoder projected into an LLM", "Better than text-only LLMs on properties", "Needs structure files and fine-tuning", "Multimodal input is future work"],
    ["Conversational LLM agent for synthesis of MOF catalysts (MOFsyn Agent)", "Lin et al.", "2025, ACS Nano", "RAG and ML agent guiding synthesis", "Faster Ni@UiO-66(Ce) catalyst optimisation", "Single reaction system", "RAG and ML combined, as in MOFChat"],
    ["The rise of generative AI for MOF design and synthesis", "Duan et al.", "2025, arXiv (perspective)", "Review of VAEs, diffusion models and LLM agents", "Roadmap to closed-loop discovery", "Feasibility and data gaps", "MOFChat sits at the screening stage"],
    ["LitMOF: LLM multi-agent for literature-validated MOF database correction", "Kim, Kim, Kim", "2025, arXiv", "Agents check CSD structures against papers", "189,567 structures; 9,227 entries repaired", "Preprint", "We also audit the data (ETL checks)"],
    ["Enhancing spatial reasoning in LLMs for MOF structure prediction (MOF-LLM)", "Pan et al.", "2026, arXiv", "Qwen-3 8B with spatial pretraining, SFT and RL", "35.78 % match rate, 0.04 s per structure", "Low match rate", "Small open LLMs can be specialised"],
    ["An LLM agent for end-to-end computational materials discovery (MAESTRO)", "Chen et al.", "2026, arXiv", "Agent mines papers, builds a database, screens MOFs", "Finds wet-flue-gas separation candidates", "Preprint", "MOFChat is a verified query layer"],
  ];
  const pages = [[0, 6], [6, 12], [12, 18]];
  pages.forEach(([a, b], p) => {
    s = slide(`Literature Review (2024-2026), part ${p + 1} of 3`, "Literature");
    const rows = LIT.slice(a, b).map((r, i) => [String(a + i + 1), bold(r[0]), r[1], r[2], r[3], r[4], r[5], { text: r[6], options: { color: H.navy } }]);
    table(s, ["#", "Paper", "Authors", "Year, venue", "Method", "Contribution", "Limitation", "Use in MOFChat"], rows,
      { x: 0.25, y: 1.0, w: 11.19, colW: [0.35, 1.95, 1.15, 1.25, 1.7, 1.6, 1.45, 1.74] });
  });

  // ===================================================== Research gap
  s = slide("Research Gap from the Literature", "Literature");
  table(s, ["Gap", "Evidence in 2024-2026 work", "What MOFChat does"], [
    [bold("Answers are rarely verified against data"), "ChatMOF, ChemCrow and LLaMP trust the LLM's final text; semantic entropy needs many samples.", "A deterministic answer validator checks IDs, numbers and comparison claims against the database."],
    [bold("Dependence on proprietary LLMs"), "Most agents use GPT-4.", "14 free or local models with fallback; works fully offline with Llama 3."],
    [bold("Few benchmarks for query planning"), "Accuracy is reported on the authors' own question sets.", "64-question development set, 20 held-out questions, model comparison and ablation."],
    [bold("Tabular DL vs trees on MOF descriptors"), "TabPFN, TabM and Grinsztajn et al. compare on generic data.", "FT-Transformer, MLP, XGBoost and GP compared on MOF regression and classification."]],
  { x: 0.4, y: 1.2, w: 10.9, colW: [2.7, 3.9, 4.3], rowH: 1.0 });

  // ===================================================== Dataset
  pres.addSection({ title: "Dataset" });
  s = slide("Dataset: CoRE MOF 2019 and Preprocessing", "Dataset");
  table(s, ["Category", "Attributes"], [["Identification", "MOF_ID (CSD refcode)"], ["Pore geometry", "LCD, PLD, LFPD (Å)"], ["Density", "Density (g/cm³)"],
    ["Surface area", "Accessible (m²/g, m²/cm³), non-accessible"], ["Porosity", "Void fraction, pore volume, non-accessible volume"], ["Chemistry", "Metal type, open metal site, OMS type"]],
  { x: 0.4, y: 1.1, w: 5.4, colW: [1.5, 3.9], rowH: 0.36 });
  T(s, "12,020 experimental MOFs and 17 columns, computed with Zeo++ using a 3.31 Å (N2) probe.", { x: 0.4, y: 4.0, w: 5.4, h: 0.5 });
  sub(s, "Preprocessing (ETL) findings", 6.0, 1.05, 5.4);
  table(s, ["Check", "Finding and action"], [["Missing values, duplicates", "None"], ["Two column pairs identical", "Duplicates dropped"],
    ["Pore volume = void fraction / density", "Derived column; documented"], ["Zero surface area (3,252 MOFs)", "All have PLD < 3.31 Å; physics rule"],
    ["Density header said cm³/g", "Values are g/cm³; label fixed"], ["2,087 multi-metal MOFs", "Separate mof_metals table"],
    ["Feature scaling", "log1p and z-score"]], { x: 6.0, y: 1.4, w: 5.4, colW: [2.6, 2.8], rowH: 0.36 });
  await img(s, fig("feat_metals.png"), 0.4, 5.25, 10.9, 2.55);

  // ===================================================== Feature extraction 1
  s = slide("Feature Extraction: Descriptor Distributions and Correlations", "Dataset");
  await img(s, fig("feat_distributions.png"), 0.3, 1.0, 7.0);
  await img(s, fig("feat_correlation.png"), 7.45, 1.0, 4.0);
  caption(s, "Pearson correlation of the ten descriptors", 7.45, 4.45, 4.0);
  const sc = DL.features.strongest_correlations.slice(0, 4).map(([a, b, c]) => `${a} and ${b} (${c >= 0 ? "+" : ""}${c.toFixed(2)})`);
  sub(s, "Observations", 0.4, 4.0, 6.8);
  bullets(s, ["Most descriptors are right-skewed, so they are log-transformed and standardised before the FT-Transformer",
    "27 % of MOFs have exactly zero accessible surface area (the spike at 0)", "Strongest correlations: " + sc.join(", "),
    "Pore volume is derived from void fraction and density, so it is left out when predicting void fraction"], { x: 0.4, y: 4.35, w: 6.9, h: 2.8 });

  // ===================================================== Feature extraction 2
  s = slide("Feature Extraction: PCA, Learned Embeddings and Reconstruction", "Dataset");
  await img(s, fig("feat_pca.png"), 0.3, 1.0, 5.6);
  await img(s, fig("feat_tsne_embeddings.png"), 6.0, 1.0, 5.4);
  await img(s, fig("feat_reconstruction_importance.png"), 0.3, 3.35, 7.0);
  const pe = DL.features.pca_explained;
  bullets(s, [[B("PCA: "), R(`the first two components explain ${pct(pe[0] + pe[1], 0)} of the variance`)],
    [B("t-SNE of the 64-d FT-Transformer embeddings: "), R("smooth surface-area gradient; metals form local clusters")],
    [B("Masked reconstruction: "), R(`R² ${f3(FTM.reconstruction_r2_masked.Surface_Area)} for surface area and ${f3(FTM.reconstruction_r2_masked.Void_Fraction)} for void fraction when hidden`)],
    [B("SHAP: "), R("pore volume and void fraction drive surface area; density drives void fraction")]], { x: 7.45, y: 3.45, w: 3.95, h: 4.2 });

  // ===================================================== Pipeline dashboard -> backend
  pres.addSection({ title: "Architecture" });
  s = slide("Overall Pipeline: Dashboard to Backend", "Architecture");
  T(s, "FRONTEND", { x: 0.3, y: 1.0, w: 2, h: 0.3, bold: true, color: H.navy });
  box(s, 0.3, 1.35, 2.2, 0.85, "Streamlit dashboard (app.py)", "FAC090");
  box(s, 0.3, 2.45, 2.2, 0.85, "User question and model choice", H.pale.yellow);
  box(s, 0.3, 6.15, 2.2, 1.2, "Answer, verified table, Pareto and SHAP plots, trace", "FAC090");
  arrow(s, 1.4, 2.2, 1.4, 2.45);
  T(s, "BACKEND (mofchat/agent.py)", { x: 2.9, y: 1.0, w: 6, h: 0.3, bold: true, color: H.navy });
  box(s, 2.95, 2.45, 2.0, 0.85, "LLM planner (JSON plan)", "E6B9B8", { border: H.red });
  box(s, 2.95, 1.35, 2.0, 0.85, "Rule parser", H.pale.grey);
  box(s, 5.3, 2.45, 2.0, 0.85, "Plan validator", H.pale.aqua);
  box(s, 7.65, 2.45, 1.75, 0.85, "Intent router", H.pale.purple);
  arrow(s, 2.5, 2.87, 2.95, 2.87); arrow(s, 3.95, 2.2, 3.95, 2.45); arrow(s, 4.95, 2.87, 5.3, 2.87); arrow(s, 7.3, 2.87, 7.65, 2.87);
  line(s, 6.3, 2.45, 6.3, 2.32, H.red, 1.5, "dash"); line(s, 4.45, 2.32, 6.3, 2.32, H.red, 1.5, "dash"); arrow(s, 4.45, 2.32, 4.45, 2.45, H.red, 1.5);
  T(s, "retry up to 2 times", { x: 5.1, y: 1.98, w: 2.0, h: 0.3, italic: true, color: H.red });
  box(s, 8.6, 1.35, 2.8, 0.85, "14 LLMs with fallback", "E6B9B8", { border: H.red });
  const tools = [["SQL and NSGA-II", H.pale.green], ["FT-Transformer and FAISS", H.pale.blue], ["XGBoost, conformal, SHAP", H.pale.peach], ["RAG: MiniLM and FAISS", H.pale.pink]];
  line(s, 8.52, 3.3, 8.52, 3.65); line(s, 3.9, 3.65, 10.2, 3.65);
  tools.forEach(([t, f], i) => { const x = 2.9 + i * 2.1; arrow(s, x + 1.0, 3.65, x + 1.0, 3.85); box(s, x, 3.85, 2.0, 0.95, t, f); line(s, x + 1.0, 4.8, x + 1.0, 5.05); });
  line(s, 3.9, 5.05, 10.2, 5.05);
  arrow(s, 6.1, 5.05, 6.1, 5.3);
  box(s, 4.6, 5.3, 3.0, 0.75, "LLM answer writer", "E6B9B8", { border: H.red });
  arrow(s, 7.6, 5.67, 8.0, 5.67);
  box(s, 8.0, 5.3, 3.4, 0.75, "Answer validator", H.pale.aqua);
  line(s, 9.7, 6.05, 9.7, 6.75); arrow(s, 9.7, 6.75, 2.5, 6.75);
  T(s, "Stored artifacts: coremof.db, embeddings.npy and index.faiss, xgb.json and ft.pt, knowledge index", { x: 2.95, y: 6.95, w: 8.4, h: 0.3, color: H.grey });
  T(s, "Red boxes use a language model; the other steps are deterministic code.", { x: 2.95, y: 7.35, w: 8.4, h: 0.3, italic: true, color: H.grey });

  // ===================================================== Offline + online pipeline
  s = slide("Pipeline Architecture: Offline Training and Online Inference", "Architecture");
  sub(s, "Offline (run once)", 0.4, 1.0, 5);
  const off = [["MOF dataset", "8064A2", "FFFFFF"], ["ETL and checks", H.pale.green], ["Feature scaling", H.pale.aqua], ["Masked FT-Transformer", H.pale.peach],
    ["Surrogate models", H.pale.blue], ["Knowledge index", H.pale.pink], ["Evaluation", H.pale.yellow]];
  off.forEach(([t, f, c], i) => { const x = 0.35 + i * 1.6; box(s, x, 1.4, 1.45, 0.9, t, f, { color: c || "000000" }); if (i < off.length - 1) arrow(s, x + 1.45, 1.85, x + 1.6, 1.85); });
  T(s, "Scripts: setup_db.py, train_ft.py, train_property_models.py, setup_vectorstore.py, evaluate.py, evaluate_dl.py", { x: 0.4, y: 2.45, w: 10.9, h: 0.3, color: H.grey });
  sub(s, "Online (per question)", 0.4, 3.0, 5);
  const on = [["User query", "FAC090"], ["Plan (LLM and rules)", "E6B9B8"], ["Validate plan", H.pale.aqua], ["Execute tools", H.pale.green],
    ["Write answer (LLM)", "E6B9B8"], ["Validate answer", H.pale.aqua], ["Show answer", "FAC090"]];
  on.forEach(([t, f], i) => { const x = 0.35 + i * 1.6; box(s, x, 3.4, 1.45, 0.9, t, f); if (i < on.length - 1) arrow(s, x + 1.45, 3.85, x + 1.6, 3.85); });
  sub(s, "Feature extraction inside the FT-Transformer", 0.4, 4.75, 8);
  const fe = [["10 descriptors, metal, OMS", H.pale.grey], ["Feature tokenizer", H.pale.aqua], ["[CLS] and 3 Transformer blocks", H.pale.blue],
    ["64-d MOF embedding", H.pale.peach], ["FAISS nearest neighbours", H.pale.green], ["Similar MOFs", "FAC090"]];
  fe.forEach(([t, f], i) => { const x = 0.35 + i * 1.87; box(s, x, 5.15, 1.7, 0.95, t, f); if (i < fe.length - 1) arrow(s, x + 1.7, 5.62, x + 1.87, 5.62); });
  T(s, "In review 1, 384-d MOF embeddings were matched to a Sentence-BERT question vector. The two were never trained together, so this path was replaced by plan, validate and SQL (exact answers rose from 9.4 % to 100 %).",
    { x: 0.4, y: 6.5, w: 10.9, h: 0.7 });

  // ===================================================== Models used (1/2)
  s = slide("Models Used (1): Language and Embedding Models", "Architecture");
  table(s, ["Model", "Type", "How it works", "Role in MOFChat"], [
    [bold("Gemini 3.1 Flash-Lite"), "LLM, cloud (free)", "Transformer decoder that predicts the next token; we prompt it with the schema, rules and 9 examples at temperature 0 in JSON mode", "Default planner and answer writer"],
    [bold("GPT-OSS 120B / 20B, Qwen 3.8 27B (Groq)"), "LLMs, cloud (free)", "Same principle; open-weight models served by Groq", "Fallback planners and writers"],
    [bold("Nemotron 3, Gemma 4 (OpenRouter)"), "LLMs, cloud (free)", "Open models through an OpenAI-compatible API", "Further fallbacks"],
    [bold("Llama 3 / 3.1 8B, Qwen 2.5 7B (Ollama)"), "LLMs, local", "Small open models running on the laptop CPU", "Offline planning and answers"],
    [bold("all-MiniLM-L6-v2 (Sentence-BERT)"), "Embedding model, 384-d", "6-layer Transformer; mean-pooled sentence vectors compared by cosine similarity", "Embeds questions and knowledge chunks for RAG"],
    [bold("FT-Transformer autoencoder"), "Embedding model, 64-d", "Each descriptor becomes a token; 30 % are masked and the [CLS] state reconstructs all ten", "MOF embeddings for similarity search"],
    [bold("FAISS"), "Vector index", "Inner product on normalised vectors equals cosine similarity; fast exact search", "Nearest-neighbour search for RAG and similarity"]],
  { x: 0.3, y: 1.05, w: 11.1, colW: [2.6, 1.7, 4.4, 2.4], rowH: 0.8 });

  // ===================================================== Models used (2/2)
  s = slide("Models Used (2): Prediction Models and Algorithms", "Architecture");
  table(s, ["Model", "Type", "How it works", "Role in MOFChat"], [
    [bold("XGBoost"), "Gradient-boosted trees", "Hundreds of small decision trees added one after another, each fitting the errors of the previous ones", "Main surrogate model; OMS classifier"],
    [bold("FT-Transformer regressor / classifier"), "Deep learning", "Same Transformer backbone with a linear head; MSE or cross-entropy loss; early stopping on validation loss", "Surface area, void fraction; OMS classification"],
    [bold("MLP classifier"), "Deep learning", "Two hidden layers of 128 ReLU units with a metal embedding; cross-entropy loss", "Deep-learning baseline for OMS"],
    [bold("Gaussian process"), "Bayesian regression", "RBF kernel with one length scale per feature plus noise; gives a mean and an uncertainty", "Regression baseline with 95 % intervals"],
    [bold("Ridge, logistic regression"), "Linear models", "Linear models with an L2 penalty", "Baselines"],
    [bold("NSGA-II"), "Multi-objective algorithm", "Sorts candidates into Pareto fronts, then prefers well-spread points (crowding distance)", "Ranks MOFs on several objectives"],
    [bold("SHAP (TreeSHAP)"), "Explainability", "Shapley values split each prediction into per-feature contributions", "Explains every prediction"],
    [bold("Split-conformal prediction"), "Uncertainty", "90th percentile of absolute errors on a calibration split gives a ± interval", "90 % prediction intervals"]],
  { x: 0.3, y: 1.05, w: 11.1, colW: [2.6, 1.7, 4.4, 2.4], rowH: 0.72 });

  // ===================================================== FT architecture
  s = slide("Model Architecture: FT-Transformer (Gorishniy et al., 2021)", "Architecture");
  const toks = ["[CLS]", "LCD", "PLD", "LFPD", "Dens.", "SA", "VF", "...", "metal"];
  toks.forEach((t, i) => box(s, 0.35 + i * 0.8, 6.55, 0.72, 0.5, t, i === 0 ? "E6B9B8" : i === 8 ? H.pale.purple : H.pale.aqua, { bold: false }));
  T(s, "Input tokens: numeric value times a learned vector plus bias, categorical embeddings and a learned [CLS] token", { x: 0.35, y: 7.15, w: 7.2, h: 0.5, italic: true, color: H.grey });
  arrow(s, 3.9, 6.55, 3.9, 6.3);
  box(s, 0.6, 3.25, 6.6, 3.05, "", H.pale.blue);
  T(s, "3 pre-norm Transformer blocks (d = 64, 4 heads)", { x: 0.8, y: 3.32, w: 6.2, h: 0.3, bold: true, align: "center" });
  ["LayerNorm", "Self-attention", "Residual add", "LayerNorm", "Feed-forward", "Residual add"].forEach((t, i) =>
    box(s, 1.2 + (i % 3) * 1.85, 3.8 + Math.floor(i / 3) * 1.15, 1.7, 0.8, t, i === 1 ? "FAC090" : "FFFFFF"));
  arrow(s, 3.9, 3.25, 3.9, 2.95);
  box(s, 2.6, 2.35, 2.6, 0.6, "LayerNorm, [CLS] (64-d)", H.pale.peach);
  [["Decoder: 10 descriptors (MSE)", 0.35], ["Linear: 1 value (MSE)", 2.75], ["Linear: logit (BCE)", 5.15]].forEach(([t, x]) => {
    arrow(s, 3.9, 2.35, x + 1.15, 1.9); box(s, x, 1.05, 2.3, 0.85, t, H.pale.green);
  });
  sub(s, "Configuration", 7.7, 1.05, 3.6, H.navy);
  table(s, ["Item", "Value"], [["Parameters (embedding)", FTM.n_params.toLocaleString()], ["Parameters (classifier)", DL.oms.ft_params.toLocaleString()],
    ["Blocks / heads / d", "3 / 4 / 64"], ["Optimiser", "AdamW, lr 0.001"], ["Batch size", "256"], ["Early stopping", "validation loss"], ["SSL masking", "30 % of tokens"],
    ["SSL training", `${FTM.epochs_trained} epochs`], ["Regressor (surface area)", `${PM.Surface_Area.ft_epochs} epochs`], ["Classifier (OMS)", `best epoch ${DL.oms.history["FT-Transformer"].best_epoch}`]],
  { x: 7.7, y: 1.4, w: 3.7, colW: [2.1, 1.6], rowH: 0.36 });
  T(s, "Heads: embedding for similarity search, regression for surface area and void fraction, classification for open metal sites.", { x: 7.7, y: 5.75, w: 3.7, h: 0.9, color: H.navy });

  // ===================================================== Planner + validator
  s = slide("LLM Planning: Plan, Validate, Execute", "Architecture");
  box(s, 0.4, 1.1, 5.6, 0.6, "\"Which zinc MOFs have high surface area and low density?\"", H.pale.yellow, { bold: false });
  arrow(s, 3.2, 1.7, 3.2, 1.95);
  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 1.95, w: 5.6, h: 2.05, fill: { color: "1F2A36" }, line: { color: "1F2A36", width: 0 } });
  T(s, '{ "intent": "search",\n  "metals": ["Zn"],\n  "objectives": [\n    {"column": "Surface_Area", "direction": "max"},\n    {"column": "Density", "direction": "min"} ],\n  "limit": 5 }',
    { x: 0.55, y: 2.05, w: 5.4, h: 1.9, fontFace: "Courier New", color: "E7EEF4" });
  arrow(s, 3.2, 4.0, 3.2, 4.25);
  box(s, 0.4, 4.25, 5.6, 1.2, "Executor: whitelisted columns, bound parameters, read-only SQL on zinc MOFs, then NSGA-II ranking for the two objectives", H.pale.green, { bold: false });
  T(s, "Intents: search, count, lookup, similar, predict, knowledge, out of scope", { x: 0.4, y: 5.7, w: 5.6, h: 0.5, color: H.navy });
  sub(s, "Validator checks", 6.4, 1.05, 5);
  bullets(s, ["Column aliases resolved from one registry", "Units, operators and percentages normalised", "Impossible or invented values rejected",
    "Thresholds not in the question become preferences", "MOF IDs not in the question dropped", "Superlatives written as constraints repaired",
    "Application presets expanded (H2, CH4, CO2, sieving, catalysis)", "Objectives not asked for in an application question dropped"], { x: 6.4, y: 1.4, w: 5.0, h: 3.6 });
  T(s, "If errors remain after two corrections, the rule-parser plan is used. If no LLM is reachable, the rules and a template answer are used.", { x: 6.4, y: 5.2, w: 5.0, h: 0.8 });

  // ===================================================== NSGA-II
  s = slide("Multi-Objective Ranking with NSGA-II", "Architecture");
  const P = JSON.parse(fs.readFileSync(path.join(HERE, "pareto.json")));
  const xs = [...P.bg.map((p) => p[0]), ...P.f23.map((p) => p[0]), ...P.f1.map((p) => p[0])];
  const nb = P.bg.length, n2 = P.f23.length, n1 = P.f1.length;
  const pad = (arr, a, b) => [...Array(a).fill(null), ...arr, ...Array(b).fill(null)];
  s.addChart(pres.charts.SCATTER, [{ name: "X", values: xs }, { name: "Candidates (sample of 700)", values: pad(P.bg.map((p) => p[1]), 0, n2 + n1) },
    { name: "Pareto fronts 2-3", values: pad(P.f23.map((p) => p[1]), nb, n1) }, { name: "Front 1 (recommended)", values: pad(P.f1.map((p) => p[1]), nb + n2, 0) }], Object.assign({
    x: 5.6, y: 1.0, w: 5.9, h: 5.4, lineSize: 0, lineDataSymbol: "circle", lineDataSymbolSize: 6, chartColors: ["BFBFBF", H.blue, H.red],
    showLegend: true, legendPos: "b", showTitle: true, title: "H2 storage: 10,226 MOFs with PLD ≥ 2.89 Å",
    showValAxisTitle: true, valAxisTitle: "Void fraction", showCatAxisTitle: true, catAxisTitle: "Surface area (m²/g)", valAxisMinVal: 0, valAxisMaxVal: 1,
    catAxisMinVal: 0, catAxisMaxVal: 9000, valGridLine: { color: "E0E0E0", size: 0.5 }, catGridLine: { style: "none" }, valAxisLabelFormatCode: "0.0" }, CHART));
  bullets(s, [[B("Domination: "), R("A beats B if A is at least as good on every objective and better on one")], [B("Non-dominated sorting: "), R("front 1 holds the MOFs no other MOF beats; remove them and repeat")],
    [B("Crowding distance: "), R("prefers MOFs in sparse regions, giving diverse trade-offs")], [B("Two objectives: "), R("exact O(n log n) sweep; the worst 25 % are screened out first")],
    [B("Speed: "), R("all 12,020 MOFs in 0.02 s (2 objectives) and 2.6 s (3)")]], { x: 0.4, y: 1.1, w: 5.0, h: 3.4 });
  table(s, ["Application", "Heuristic rule"], [["H2 storage", "PLD ≥ 2.89 Å; max surface area and void fraction"], ["CH4 storage", "PLD ≥ 3.80 Å; max volumetric area and void fraction"],
    ["CO2 capture", "Open metal site; PLD ≥ 3.30 Å; min LCD"], ["Separation A/B", "Kinetic diameter of A ≤ PLD ≤ that of B"], ["Catalysis", "Open metal site; PLD ≥ 5 Å"]],
  { x: 0.4, y: 4.75, w: 5.0, colW: [1.4, 3.6], rowH: 0.4 });

  // ===================================================== Results: benchmark
  pres.addSection({ title: "Results" });
  const sys = SUM.benchmark.systems, ho = SUM.heldout.systems;
  const names = ["Review-1 two-tower (shipped)", "Rules planner (no LLM)", "LLM planner, single shot (no validator)", "LLM planner + validator", "Hybrid (default)"];
  const short = ["Review-1 two-tower", "Rules only", "LLM single shot", "LLM + validator", "Hybrid (default)"];
  s = slide("Results: Retrieval Benchmark", "Results");
  const barOpts = (title, colors) => Object.assign({ barDir: "col", barGapWidthPct: 60, chartColors: colors, showValue: true, dataLabelPosition: "outEnd",
    dataLabelFormatCode: "General\"%\"", showLegend: true, legendPos: "t", showTitle: true, title, valAxisMaxVal: 115, valAxisMinVal: 0, valAxisHidden: true,
    valGridLine: { style: "none" }, catGridLine: { style: "none" } }, CHART);
  s.addChart(pres.charts.BAR, [{ name: "Development (64)", labels: short, values: names.map((n) => sys[n].result_accuracy) },
    { name: "Held-out (20)", labels: short, values: names.map((n) => ho[n].result_accuracy) }],
  Object.assign({ x: 0.3, y: 1.0, w: 6.6, h: 4.6 }, barOpts("Exact answer match (%), Gemini 3.1 Flash-Lite", ["A6A6A6", H.blue])));
  s.addChart(pres.charts.BAR, [{ name: "Held-out", labels: ["Alone", "+ validator", "+ hybrid"], values: [65, 70, 80] },
    { name: "Development", labels: ["Alone", "+ validator", "+ hybrid"], values: [85.9, 93.8, 100] }],
  Object.assign({ x: 7.05, y: 1.0, w: 4.35, h: 4.6 }, barOpts("Ablation with offline Llama 3 8B", [H.red, "A6A6A6"])));
  bullets(s, [`An answer counts as correct only if it returns exactly the MOFs of a hand-written gold plan. Constraint precision@k on the held-out set: review 1 ${ho[names[0]].constraint_precision_at_k} %, hybrid ${ho[names[4]].constraint_precision_at_k} %.`,
    "The rules were tuned on the development set, so the held-out questions (written later, never used for tuning) give the fair estimate.",
    "The validator and hybrid planner add 15 points for the offline model and cost less than 0.01 s; for the cloud model they change nothing.",
    "ChatMOF reports 96.9 % on its own search questions; the question sets differ."], { x: 0.4, y: 5.85, w: 11.0, h: 1.9 });

  // ===================================================== Results: LLM comparison
  s = slide("Results: Free LLM Comparison and Answer Validation", "Results");
  table(s, ["Model", "Held-out alone", "Held-out hybrid", "Dev hybrid", "Median call", "Provider errors"], [
    [bold("Gemini 3.1 Flash-Lite (default)"), "100 %", "100 %", "100 %", "1.5 s", "13 / 84"], ["GPT-OSS 120B (Groq)", "95 %", "95 %", "100 %", "2.4-4.7 s", "0"],
    ["Qwen 3.8 27B (Groq)", "95 %", "95 %", "100 %", "20 s", "0"], ["Nemotron 3 Super 120B", "95 %", "95 %", "-", "2.0 s", "0"], ["Llama 3 8B (local)", "65 %", "80 %", "100 %", "1.5 s", "0"],
    ["Gemini 3.5 Flash", "-", "-", "-", "-", "64 / 84 (quota)"]], { x: 0.3, y: 1.05, w: 11.1, colW: [3.4, 1.5, 1.5, 1.3, 1.5, 1.9], rowH: 0.38, align: "center" });
  sub(s, "Answer validation (16 full answers per model)", 0.4, 4.0, 6.6);
  table(s, ["Model", "Drafts with a problem", "Rewritten", "Still flagged", "s per answer"], [["Gemini 3.1 Flash-Lite", "0 of 16", "0", "0", "9.9"],
    ["Llama 3 8B (local)", "2 of 16", "1", "0", "9.3"], ["GPT-OSS 120B", "2 of 16", "2", "1", "30.2"], ["Qwen 3.8 27B", "0 of 16", "0", "0", "26.4"]],
  { x: 0.3, y: 4.35, w: 6.7, colW: [2.1, 1.5, 1.0, 1.1, 1.0], rowH: 0.38, align: "center" });
  sub(s, "Examples caught by the validator", 7.25, 4.0, 4.2);
  bullets(s, ["Llama 3 invented two densities and a \"90 %\"; the ID OFEUN06 was corrected to OFERUN06", "GPT-OSS 120B claimed \"Pareto front 1\" for MOFs ranked on front 2",
    "Llama 3 named MOFs that do not exist (\"MOF-210\") in a prediction answer", "GPT-OSS cited a prompt header \"[WHY]\" as a source; it is now removed"], { x: 7.25, y: 4.35, w: 4.15, h: 3.3 });

  // ===================================================== Results: OMS classification
  const om = DL.oms.models;
  const order = ["Majority baseline", "Logistic regression", "XGBoost", "MLP", "FT-Transformer"];
  s = slide("Results: Open-Metal-Site Classification (DL vs ML)", "Results");
  table(s, ["Model", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC", "PR-AUC"], order.map((n) => [bold(n),
    f3(om[n].accuracy), f3(om[n].precision), f3(om[n].recall), f3(om[n].f1), f3(om[n].roc_auc), f3(om[n].pr_auc)]),
  { x: 0.3, y: 1.05, w: 11.1, colW: [3.0, 1.35, 1.35, 1.35, 1.35, 1.35, 1.35], rowH: 0.36, align: "center" });
  await img(s, fig("oms_roc_pr.png"), 0.3, 3.45, 8.3, 4.3);
  T(s, [B("Task: ", { color: H.navy }), R(`predict whether a MOF has an open metal site from its 10 geometric descriptors and primary metal. ${pct(DL.oms.positive_rate)} of MOFs have one. OMS_Type is not used as an input.`)],
    { x: 8.8, y: 3.5, w: 2.65, h: 2.0 });
  T(s, [B("Split: ", { color: H.navy }), R(`${DL.oms.split.train} / ${DL.oms.split.val} / ${DL.oms.split.test} MOFs (train / validation / test, stratified)`)], { x: 8.8, y: 5.6, w: 2.65, h: 0.8 });
  T(s, [B("Use: ", { color: H.navy }), R("the CO2-capture preset requires an open metal site.")], { x: 8.8, y: 6.5, w: 2.65, h: 0.6 });

  // ===================================================== Results: confusion matrices
  s = slide("Results: Confusion Matrices of the OMS Classifiers", "Results");
  await img(s, fig("oms_confusion.png"), 0.3, 1.05, 11.1);
  const cmTxt = ["XGBoost", "MLP", "FT-Transformer"].map((n) => { const [[tn, fp], [fn, tp]] = om[n].confusion; return [n, tn, fp, fn, tp]; });
  table(s, ["Model", "True negative", "False positive", "False negative", "True positive", "Train / val / test accuracy"],
    cmTxt.map(([n, tn, fp, fn, tp]) => [bold(n), String(tn), String(fp), String(fn), String(tp), om[n].acc_train_val_test.map(f3).join(" / ")]),
  { x: 0.3, y: 4.25, w: 11.1, colW: [2.4, 1.6, 1.6, 1.6, 1.6, 2.3], rowH: 0.38, align: "center" });
  bullets(s, [`All trained classifiers beat the majority baseline (${pct(om["Majority baseline"].accuracy)} accuracy, ROC-AUC 0.50). XGBoost is best and the two deep-learning models are close behind.`,
    "The gap between train and test accuracy shows overfitting; early stopping on validation loss limits it for the deep models.",
    "Whether a metal site is open depends on coordination chemistry that pore geometry and metal type only partly describe, so accuracy levels off near 75 %."], { x: 0.4, y: 6.0, w: 11.0, h: 1.7 });

  // ===================================================== Results: classification learning curves
  s = slide("Results: Train, Validation and Test Accuracy and Loss", "Results");
  await img(s, fig("oms_learning_curves.png"), 0.4, 1.0, 10.9, 6.35);
  const hFT = DL.oms.history["FT-Transformer"];
  T(s, `Blue: train, red: validation, green dashed: test, dotted: best epoch. FT-Transformer best epoch ${hFT.best_epoch} of ${hFT.val_loss.length}; MLP ${DL.oms.history.MLP.best_epoch}; XGBoost best round ${DL.oms.history.XGBoost.best_epoch}.`,
    { x: 0.4, y: 7.45, w: 10.9, h: 0.4, color: H.grey });

  // ===================================================== Results: regression
  s = slide("Results: Property Prediction (Regression)", "Results");
  const regModels = ["Mean baseline", "Ridge", "Gaussian Process", "XGBoost", "FT-Transformer"];
  s.addChart(pres.charts.BAR, [{ name: "Surface area", labels: regModels, values: regModels.map((m) => Math.max(0, PM.Surface_Area.models[m].test_all.R2)) },
    { name: "Void fraction", labels: regModels, values: regModels.map((m) => Math.max(0, PM.Void_Fraction.models[m].test_all.R2)) }], Object.assign({
    x: 0.3, y: 1.0, w: 5.4, h: 3.6, barDir: "bar", barGapWidthPct: 50, chartColors: [H.blue, "A6A6A6"], showValue: true, dataLabelPosition: "outEnd",
    dataLabelFormatCode: "0.000", showLegend: true, legendPos: "b", showTitle: true, title: "Test R² (held-out 10 %)", valAxisMaxVal: 1.2, valAxisMinVal: 0,
    valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, catAxisOrientation: "maxMin" }, CHART));
  await img(s, path.join(HERE, "parity_xgb_ft.png"), 5.9, 1.05, 5.5);
  caption(s, "Predicted vs actual surface area on test MOFs", 5.9, 3.85, 5.5);
  const sa = PM.Surface_Area, vf = PM.Void_Fraction, rg = DL.regression;
  const xs3 = (t) => ["train", "val", "test"].map((k) => f3(rg[t].xgb_production_split_metrics[k].R2)).join(" / ");
  const fts = (t) => [rg[t].ft_final.train_r2, rg[t].ft_final.val_r2, rg[t].ft_final.test_r2_accessible].map(f3).join(" / ");
  table(s, ["Target", "XGBoost MAE", "XGBoost R² train / val / test *", "FT R² train / val / test *", "90 % interval coverage", "GP 95 % coverage"], [
    [bold("Surface area (m²/g)"), sa.models.XGBoost.test_all.MAE.toFixed(1), xs3("Surface_Area"), fts("Surface_Area"), pct(sa.conformal.test_coverage), pct(sa.gpr.coverage_95)],
    [bold("Void fraction"), vf.models.XGBoost.test_all.MAE.toFixed(3), xs3("Void_Fraction"), fts("Void_Fraction"), pct(vf.conformal.test_coverage), pct(vf.gpr.coverage_95)]],
  { x: 0.3, y: 4.85, w: 11.1, colW: [2.0, 1.3, 2.5, 2.5, 1.5, 1.3], rowH: 0.4, align: "center" });
  T(s, `* R² on MOFs with accessible pores; the physics rule handles the zeros exactly (${pct(sa.hurdle.rule_accuracy_test)} on test). XGBoost trains in ${sa.train_seconds.XGBoost} s, the FT-Transformer in ${sa.train_seconds["FT-Transformer"]} s.`,
    { x: 0.3, y: 6.5, w: 11.1, h: 0.5, color: H.grey });
  T(s, "In the application each prediction shows the value, the 90 % interval, the FT-Transformer value and the SHAP contributions.", { x: 0.3, y: 7.1, w: 11.1, h: 0.4, color: H.navy });

  // ===================================================== Results: regression curves
  s = slide("Results: Regression Learning Curves", "Results");
  await img(s, fig("regression_learning_curves.png"), 0.4, 1.0, 10.9, 6.35);
  T(s, `Blue: train, red: validation, green dashed: test R². FT-Transformer best epoch ${rg.Surface_Area.ft_best_epoch} (surface area) and ${rg.Void_Fraction.ft_best_epoch} (void fraction); XGBoost best round ${rg.Surface_Area.xgb_best_round} and ${rg.Void_Fraction.xgb_best_round}.`,
    { x: 0.4, y: 7.45, w: 10.9, h: 0.4, color: H.grey });

  // ===================================================== Results: intent + off-topic
  const it = DL.intent, ot = DL.offtopic;
  s = slide("Results: Intent Classification and Off-Topic Detection", "Results");
  await img(s, fig("intent_confusion.png"), 0.3, 1.0, 11.1, 3.65);
  await img(s, fig("offtopic_roc.png"), 0.3, 4.75, 7.9, 2.35);
  const iRows = ["Rules planner (no LLM)", "Llama 3 8B (local), alone", "Llama 3 8B (local), hybrid", "Gemini 3.1 Flash-Lite, hybrid"];
  table(s, ["Planner", "Accuracy", "Macro F1"], iRows.map((n) => [n.replace(" (local)", "").replace("Gemini 3.1 ", "").replace(" (no LLM)", ""), f3(it[n].accuracy), f3(it[n].macro_f1)]),
    { x: 8.35, y: 4.75, w: 3.1, colW: [1.3, 0.9, 0.9], rowH: 0.36, align: "center" });
  T(s, `Off-topic detector: ROC-AUC ${f3(ot.roc_auc)}, accuracy ${f3(ot.accuracy)} on ${ot.n_in_domain} MOF questions and ${ot.n_off_topic} off-topic questions (cosine threshold ${ot.threshold}).`,
    { x: 0.3, y: 7.25, w: 11.1, h: 0.5, color: H.grey });

  // ===================================================== Results: explainability + similarity
  s = slide("Results: Explainability and Similarity Search", "Results");
  await img(s, path.join(PROJ, "artifacts/property_models/shap_summary_Surface_Area.png"), 0.3, 1.0, 5.6);
  await img(s, fig("oms_ft_attention.png"), 6.1, 1.0, 5.3);
  const simm = FTM.similarity;
  table(s, ["Neighbours from (1,000 queries)", "Descriptor gap (σ)", "Same metal", "Same OMS flag"], [
    [bold("FT-Transformer embedding"), f3(simm.ft_embedding.mean_abs_descriptor_diff_std), pct(simm.ft_embedding.same_metal_rate), pct(simm.ft_embedding.same_open_metal_site_rate)],
    ["k-NN on raw descriptors", f3(simm.raw_descriptor_knn.mean_abs_descriptor_diff_std), pct(simm.raw_descriptor_knn.same_metal_rate), pct(simm.raw_descriptor_knn.same_open_metal_site_rate)],
    ["Random MOFs", f3(simm.random.mean_abs_descriptor_diff_std), pct(simm.random.same_metal_rate), pct(simm.random.same_open_metal_site_rate)]],
  { x: 0.3, y: 4.45, w: 7.0, colW: [2.8, 1.5, 1.2, 1.5], rowH: 0.38, align: "center" });
  bullets(s, ["Pore volume and void fraction dominate surface-area predictions; density dominates void fraction", "Knowledge retrieval: hit@1 75 %, hit@3 83 %",
    "Every prediction in the application shows its SHAP contributions and a 90 % interval"], { x: 7.55, y: 4.5, w: 3.85, h: 2.8 });

  // ===================================================== Results: limitations addressed
  s = slide("Results: ChatMOF Limitations Addressed", "Results");
  table(s, ["ChatMOF limitation", "What MOFChat does", "Status"], [["No intrinsic knowledge", "RAG over curated notes and the ChatMOF paper", "Done"],
    ["Token-context limits", "SQL first; the LLM sees at most 10 rows", "Done"], ["Logic errors in LLM code", "JSON plan, validator, whitelisted SQL", "Done"],
    ["Restricted search space", "All 12,020 MOFs searched and ranked", "Done"], ["Narrow topology coverage", "All CoRE-MOF structures, 65 metals", "Done *"],
    ["Pretrained model per property", "Own surrogate models and OMS classifier trained on the table", "Done *"], ["General, non-fine-tuned LLM", "Domain prompts, few-shot examples, presets", "Partly"],
    ["High compute cost", "Millisecond screening; XGBoost trains in 0.25 s", "Done"], ["Unvalidated output", "Answer validator, intervals, SHAP, benchmark", "Done"]].map((r) =>
    [bold(r[0]), r[1], { text: r[2], options: { bold: true, color: r[2] === "Partly" ? H.red : H.navy, align: "center" } }]),
  { x: 0.4, y: 1.1, w: 10.9, colW: [3.4, 6.0, 1.5], rowH: 0.55 });
  T(s, "* for recommending existing MOFs and for properties in the table; no structure generation and no gas uptake without uptake data", { x: 0.4, y: 6.6, w: 10.9, h: 0.4, color: H.grey });

  // ===================================================== Application
  pres.addSection({ title: "Application" });
  s = slide("Application: Streamlit Dashboard", "Application");
  await img(s, path.join(HERE, "shot_answer.png"), 0.35, 1.05, 5.4);
  await img(s, path.join(HERE, "shot_pareto.png"), 5.95, 1.05, 5.4);
  caption(s, "Verified result table for a zinc MOF question", 0.35, 3.75, 5.4);
  caption(s, "NSGA-II Pareto plot for the same question", 5.95, 3.75, 5.4);
  const appPages = [["Chat", "Answer, verified table, Pareto plot, SHAP, sources, plan, SQL, validator report, model used"], ["Explore and optimise", "Filters and two-objective NSGA-II with a Pareto plot"],
    ["Predict and explain", "Prediction, 90 % interval, SHAP bars, FT-Transformer attention"], ["Evaluation", "Benchmark, model comparison, parity and SHAP plots"], ["About", "Method summary and data sources"]];
  table(s, ["Page", "What it shows"], appPages.map((p) => [bold(p[0]), p[1]]), { x: 0.35, y: 4.3, w: 11.0, colW: [2.3, 8.7], rowH: 0.38 });
  T(s, "Sidebar: choice of language model (or none), planner mode (hybrid, LLM or rules), and the status of every component.", { x: 0.35, y: 6.75, w: 11.0, h: 0.5, color: H.navy });

  // ===================================================== Conclusion
  pres.addSection({ title: "Conclusion" });
  s = slide("Conclusion and Future Work", "Conclusion");
  sub(s, "Conclusion", 0.4, 1.05, 5.4, H.navy);
  bullets(s, ["Exact answers over all 12,020 MOFs: 5 % (review 1) to 100 % on held-out questions with the default model, 80 % fully offline",
    "Validated LLM planning with 14 free or local models and automatic fallback", "NSGA-II multi-objective ranking with application presets",
    `Surface-area surrogate: R² ${f3(sa.models.XGBoost.test_all.R2)}; the 90 % interval covers ${pct(sa.conformal.test_coverage)} of test MOFs`,
    `Open-metal-site classification: ROC-AUC ${f3(om.XGBoost.roc_auc)} (XGBoost), ${f3(om["FT-Transformer"].roc_auc)} (FT-Transformer), ${f3(om.MLP.roc_auc)} (MLP)`,
    "An answer validator checks every MOF ID, number and comparison in the LLM's answer"], { x: 0.4, y: 1.4, w: 5.5, h: 5.8 });
  sub(s, "Limitations and future work", 6.2, 1.05, 5.2, H.red);
  table(s, ["Limitation", "Future work"], [["No gas-uptake labels", "Add GCMC uptake data and reuse the surrogate pipeline"], ["No structure generation", "Diffusion or GA generator (e.g. MOFDiff)"],
    ["Offline model at 80 %", "LoRA fine-tuning of Llama 3 on plan examples"], ["Free-text reasoning not checked", "Sentence-level checks such as semantic entropy"],
    ["Heuristic presets", "Learned rules once uptake data exists"], ["Descriptor-only embeddings", "Structure or multimodal encoders (L2M3OF)"]],
  { x: 6.2, y: 1.4, w: 5.2, colW: [2.0, 3.2], rowH: 0.7 });

  // ===================================================== References (2 slides)
  const refs = [
    "Y. Kang and J. Kim, \"ChatMOF: an artificial intelligence system for predicting and generating metal-organic frameworks using large language models,\" Nat. Commun., vol. 15, 4705, 2024.",
    "Y. G. Chung et al., \"Advances, updates, and analytics for the computation-ready, experimental MOF database: CoRE MOF 2019,\" J. Chem. Eng. Data, vol. 64, pp. 5985-5998, 2019.",
    "Y. Gorishniy, I. Rubachev, V. Khrulkov and A. Babenko, \"Revisiting deep learning models for tabular data,\" NeurIPS, 2021.",
    "L. Grinsztajn, E. Oyallon and G. Varoquaux, \"Why do tree-based models still outperform deep learning on typical tabular data?\" NeurIPS Datasets and Benchmarks, 2022.",
    "K. Deb, A. Pratap, S. Agarwal and T. Meyarivan, \"A fast and elitist multiobjective genetic algorithm: NSGA-II,\" IEEE Trans. Evol. Comput., vol. 6, pp. 182-197, 2002.",
    "S. M. Lundberg and S.-I. Lee, \"A unified approach to interpreting model predictions,\" NeurIPS, 2017.",
    "A. M. Bran et al., \"Augmenting large language models with chemistry tools,\" Nat. Mach. Intell., vol. 6, 2024.",
    "X. Fu, T. Xie, A. S. Rosen, T. Jaakkola and J. Smith, \"MOFDiff: coarse-grained diffusion for metal-organic framework design,\" ICLR, 2024.",
    "S.-A. Chen et al., \"TableRAG: million-token table understanding with language models,\" NeurIPS, 2024.",
    "Z. Wang et al., \"Chain-of-Table: evolving tables in the reasoning chain for table understanding,\" ICLR, 2024.",
    "S. Farquhar, J. Kossen, L. Kuhn and Y. Gal, \"Detecting hallucinations in large language models using semantic entropy,\" Nature, vol. 630, pp. 625-630, 2024.",
    "W. Lee, Y. Kang, T. Bae and J. Kim, \"Harnessing large language models to collect and analyze MOF property data set,\" J. Am. Chem. Soc., vol. 147, pp. 3943-3958, 2025.",
    "T. M. Pruyn et al., \"MOF-ChemUnity: literature-informed large language models for metal-organic framework research,\" J. Am. Chem. Soc., 2025.",
    "N. Hollmann et al., \"Accurate predictions on small data with a tabular foundation model,\" Nature, vol. 637, pp. 319-326, 2025.",
    "Y. Gorishniy, A. Kotelnikov and A. Babenko, \"TabM: advancing tabular deep learning with parameter-efficient ensembling,\" ICLR, 2025.",
    "Y. Chiang, E. Hsieh, C.-H. Chou and J. Riebesell, \"LLaMP: large language model made powerful for high-fidelity materials knowledge retrieval,\" EMNLP, 2025.",
    "T. J. Inizan et al., \"System of agentic AI for the discovery of metal-organic frameworks,\" arXiv:2504.14110, 2025.",
    "J. Cui et al., \"L2M3OF: a large language multimodal model for metal-organic frameworks,\" arXiv:2510.20976, 2025.",
    "J. Lin et al., \"Conversational large-language-model AI agent for accelerated synthesis of MOF catalysts in olefin hydrogenation,\" ACS Nano, vol. 19, pp. 23840-23858, 2025.",
    "C. Duan et al., \"The rise of generative AI for metal-organic framework design and synthesis,\" arXiv:2508.13197, 2025.",
    "H. Kim, D. Kim and J. Kim, \"LitMOF: an LLM multi-agent for literature-validated MOF database correction and expansion,\" arXiv:2512.01693, 2025.",
    "M. Pan et al., \"Enhancing spatial reasoning in large language models for MOF structure prediction,\" arXiv:2601.09285, 2026.",
    "Y. Chen et al., \"An LLM agent for end-to-end computational materials discovery,\" arXiv:2608.20434, 2026."];
  [[0, 12], [12, refs.length]].forEach(([a, b], p) => {
    s = slide(`References (${p + 1} of 2)`, "Conclusion");
    T(s, refs.slice(a, b).map((r, i) => R(`[${a + i + 1}] ${r}`, { breakLine: a + i < b - 1, paraSpaceAfter: 5 })), { x: 0.4, y: 1.05, w: 10.9, h: 6.8 });
  });

  // ===================================================== Thank you
  s = pres.addSlide({ masterName: "TEMPLATE_BLANK", sectionTitle: "Conclusion" });
  T(s, "Thank You", { x: 0.5, y: 2.8, w: 10.69, h: 1.5, fontSize: 80, bold: true, color: "00B0F0", align: "center", valign: "middle" });
  T(s, "github.com/Sai-Mohith24/MOFChat-AI-Driven-Material-Recommendation-", { x: 0.5, y: 4.6, w: 10.69, h: 0.4, color: H.grey, align: "center" });

  // ===================================================== Appendix
  pres.addSection({ title: "Appendix" });
  s = slide("Appendix: Physics Rule as a Classifier", "Appendix");
  await img(s, fig("physics_rule.png"), 0.4, 1.0, 10.9, 5.6);
  T(s, `Rule: surface area = 0 if PLD < ${DL.physics.threshold_A.toFixed(4)} Å. Test accuracy ${pct(DL.physics.accuracy, 2)} on ${DL.physics.n_test} MOFs.`, { x: 0.4, y: 7.0, w: 10.9, h: 0.4, bold: true, color: H.navy });

  s = slide("Appendix: Application Screenshots", "Appendix");
  await img(s, path.join(HERE, "app_home.png"), 0.3, 1.0, 5.5);
  await img(s, path.join(HERE, "app_pareto.png"), 5.95, 1.0, 5.5);
  caption(s, "Chat page with model choice and system status", 0.3, 4.5, 5.5);
  caption(s, "Pareto plot for the zinc MOF question", 5.95, 4.5, 5.5);
  await img(s, path.join(HERE, "app_answer.png"), 3.1, 4.9, 5.5, 3.0);

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
}
build().catch((e) => { console.error(e); process.exit(1); });

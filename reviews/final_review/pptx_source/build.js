// MOFChat final-review deck in the style of the review-1 template (A4 landscape, Amrita logo,
// blue heading bars, Arial). Numbers are read from the project's result files at build time.
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
const W = 11.69;

pres.defineSlideMaster({
  title: "TEMPLATE_CONTENT",
  background: { color: "FFFFFF" },
  objects: [
    { rect: { x: 0.25, y: 0.22, w: 11.19, h: 0.62, fill: { color: H.bar }, line: { color: H.bar, width: 0 } } },
    { placeholder: { options: { name: "title", type: "title", x: 0.4, y: 0.22, w: 10.9, h: 0.62, fontSize: 24, bold: true,
      color: C.text1, fontFace: "Arial", valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 10.85, y: 7.9, w: 0.55, h: 0.25, fontSize: 9, color: "7F7F7F", align: "right" },
});
pres.defineSlideMaster({ title: "TEMPLATE_BLANK", background: { color: "FFFFFF" }, objects: [] });

// ---------------------------------------------------------------- helpers
const T = (s, t, o) => s.addText(t, Object.assign({ isTextBox: true, margin: 0, fontFace: "Arial", color: C.text1, fontSize: 14, valign: "top" }, o));
const B = (t, o = {}) => ({ text: t, options: Object.assign({ bold: true }, o) });
const R = (t, o = {}) => ({ text: t, options: o });
function slide(title, section, notes) {
  const s = pres.addSlide({ masterName: "TEMPLATE_CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  if (notes) s.addNotes(notes);
  return s;
}
function bullets(s, items, o) {
  const runs = items.map((it, i) => {
    const arr = Array.isArray(it) ? it : [it];
    return arr.map((r, j) => {
      const isObj = typeof r === "object";
      const opts = Object.assign({}, isObj ? r.options : {});
      if (j === 0) Object.assign(opts, { bullet: { indent: 14 }, paraSpaceAfter: 6 });
      if (j === arr.length - 1 && i < items.length - 1) opts.breakLine = true;
      return { text: isObj ? r.text : r, options: opts };
    });
  }).flat();
  T(s, runs, Object.assign({ fontSize: 14 }, o));
}
function sub(s, t, x, y, w, color = H.red) { T(s, t, { x, y, w, h: 0.32, fontSize: 15, bold: true, color }); }
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
  T(s, text, { x: x + 0.05, y, w: w - 0.1, h, align: "center", valign: "middle", fontSize: o.fs || 11, bold: o.bold !== false,
    color: o.color || "000000" });
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
function table(s, header, rows, o) {
  const body = rows.map((r, i) => r.map((c) => {
    const cell = typeof c === "object" ? c : { text: String(c), options: {} };
    cell.options = Object.assign({ fill: { color: i % 2 ? "FFFFFF" : H.band } }, cell.options);
    return cell;
  }));
  s.addTable([header.map((h) => (typeof h === "object" ? h : th(h))), ...body],
    Object.assign({ fontFace: "Arial", fontSize: 12, color: "000000", border: { type: "solid", pt: 0.75, color: H.line },
      margin: [2, 5, 2, 5], valign: "middle" }, o));
}
const pct = (v, d = 1) => (100 * v).toFixed(d) + " %";
const f3 = (v) => Number(v).toFixed(3);

async function build() {
  // ===================================================== 1. Title
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "TEMPLATE_BLANK", sectionTitle: "Introduction" });
  await img(s, path.join(HERE, "amrita_logo.png"), 3.16, 0.9, 5.4);
  s.addShape(pres.shapes.RECTANGLE, { x: 1.3, y: 2.65, w: 9.1, h: 1.55, fill: { color: "E6B9B8" }, line: { color: "E6B9B8", width: 0 } });
  T(s, "MOFChat: Explainable, Data-Grounded MOF Recommendation with Validated LLM Planning, Multi-Objective Optimisation and Deep-Learning Surrogates",
    { x: 1.5, y: 2.65, w: 8.7, h: 1.55, fontSize: 21, fontFace: "Arial Black", align: "center", valign: "middle" });
  T(s, "22AIE452 – Data Driven Material Modeling and Simulation  ·  Final Review", { x: 1.3, y: 4.35, w: 9.1, h: 0.4, fontSize: 15, color: "808080", align: "center" });
  T(s, "Team_09", { x: 1.3, y: 4.95, w: 9.1, h: 0.4, fontSize: 18, bold: true, align: "center", fontFace: "Arial" });
  const team = ["Amrutha T – 24255", "Charan Tej Reddy Y – 24259", "Poojitha D – 24263", "Enku Sai Mohith – 24316", "Ramu Jahna Bindu – 24249"];
  T(s, team.map((t, i) => R(t, { breakLine: i < team.length - 1 })), { x: 3.85, y: 5.45, w: 4.0, h: 1.9, fontSize: 14, align: "center", paraSpaceAfter: 3 });
  s.addNotes("Introduce the team. One sentence: MOFChat recommends metal-organic frameworks from the 12,020-MOF CoRE-MOF database through plain-English questions, and checks every number in its answers against the data.");

  // ===================================================== 2. Outline
  s = slide("Outline", "Introduction", "The talk follows the usual paper order. Results include classification (accuracy, ROC-AUC, confusion matrices), regression and learning curves.");
  const outline = [["Introduction", "MOFs, problem statement, base paper (ChatMOF)"], ["Objectives & Novelty", "What we set out to do and how we improve on ChatMOF"],
    ["Literature Review", "18 verified papers, 2024–2026"], ["Dataset & Feature Extraction", "CoRE MOF 2019, preprocessing, descriptor and embedding analysis"],
    ["Pipeline & Architecture", "Dashboard-to-backend pipeline, models used, FT-Transformer architecture"],
    ["Results", "Retrieval benchmark, DL classification (accuracy, ROC, confusion matrix), regression, learning curves"],
    ["Application, Conclusion & Future Work", "Streamlit app, limitations, references"]];
  outline.forEach(([h, d], i) => {
    const y = 1.2 + i * 0.92;
    s.addShape(pres.shapes.OVAL, { x: 0.8, y, w: 0.62, h: 0.62, fill: { color: H.blue }, line: { color: H.blue, width: 0 } });
    T(s, String(i + 1), { x: 0.8, y, w: 0.62, h: 0.62, align: "center", valign: "middle", fontSize: 18, bold: true, color: "FFFFFF" });
    T(s, h, { x: 1.65, y: y - 0.02, w: 9, h: 0.36, fontSize: 18, bold: true, color: H.navy });
    T(s, d, { x: 1.65, y: y + 0.33, w: 9, h: 0.3, fontSize: 13, color: H.grey });
  });

  // ===================================================== 3. Introduction
  s = slide("Introduction", "Introduction", "MOFs are crystalline porous materials: metal nodes joined by organic linkers. Choosing one for an application means searching thousands of structures on several properties at once. MOFChat lets a user ask in plain English and returns exact, checked answers.");
  T(s, [R("Metal–Organic Frameworks (MOFs) are crystalline porous materials made by linking metal ions with organic molecules, creating microscopic cages. Their tunable pores make them candidates for "),
    B("carbon capture, hydrogen and methane storage, gas separation and catalysis"), R(".")], { x: 0.4, y: 1.1, w: 7.0, h: 1.3, fontSize: 15 });
  T(s, [R("Selecting the right MOF is hard: the CoRE-MOF database alone has "), B("12,020 MOFs"), R(", and a good choice trades off several properties (surface area, pore size, density, metal sites) and needs domain knowledge.")],
    { x: 0.4, y: 2.45, w: 7.0, h: 1.1, fontSize: 15 });
  sub(s, "Problem statement", 0.4, 3.7, 7);
  T(s, "Existing LLM agents (ChatMOF) make MOF search conversational, but they write code that can fail, depend on paid models, hit token limits and return numbers that nobody checks against the data.",
    { x: 0.4, y: 4.05, w: 7.0, h: 1.1, fontSize: 15 });
  sub(s, "Our aim", 0.4, 5.3, 7);
  T(s, "A conversational assistant that answers MOF questions exactly from the full database, ranks trade-offs, predicts properties with uncertainty and explanation, runs on free or offline models, and verifies its own answers.",
    { x: 0.4, y: 5.65, w: 7.0, h: 1.2, fontSize: 15 });
  await img(s, path.join(HERE, "mof_structure.jpg"), 8.0, 1.3, 3.1);
  T(s, "Example MOF framework: metal nodes (cages) joined by organic linkers", { x: 7.8, y: 4.75, w: 3.5, h: 0.6, fontSize: 11, italic: true, color: H.grey, align: "center" });
  [["12,020", "MOFs"], ["65", "metals"], ["27 %", "zero accessible area"]].forEach(([n, l], i) => {
    T(s, n, { x: 7.6 + i * 1.3, y: 5.6, w: 1.25, h: 0.5, fontSize: 22, bold: true, color: H.navy, align: "center" });
    T(s, l, { x: 7.6 + i * 1.3, y: 6.1, w: 1.25, h: 0.5, fontSize: 11, color: H.grey, align: "center" });
  });

  // ===================================================== 4. Base paper
  s = slide("Base Paper: ChatMOF (Kang & Kim, Nat. Commun., 2024)", "Introduction",
    "ChatMOF is our base paper: a GPT-4 agent that plans tool calls. Its own analysis lists nine limitations; we address seven fully.");
  sub(s, "What the base paper did", 0.4, 1.05, 5.4);
  bullets(s, ["GPT-4 agent that plans tool calls (ReAct)", "Search: LLM writes pandas code over the CoRE-MOF table", "Prediction: MOFTransformer (one fine-tuned model per property)",
    "Generation: genetic algorithm with PORMAKE"], { x: 0.4, y: 1.45, w: 5.4, h: 2.0 });
  [["96.9 %", "search"], ["95.7 %", "prediction"], ["87.5 %", "generation"]].forEach(([n, l], i) => {
    T(s, n, { x: 0.45 + i * 1.8, y: 3.6, w: 1.7, h: 0.55, fontSize: 24, bold: true, color: H.navy });
    T(s, l + " accuracy", { x: 0.45 + i * 1.8, y: 4.15, w: 1.7, h: 0.3, fontSize: 11, color: H.grey });
  });
  T(s, "https://www.nature.com/articles/s41467-024-48998-4", { x: 0.4, y: 4.7, w: 5.4, h: 0.3, fontSize: 11, color: "0000FF", underline: true,
    hyperlink: { url: "https://www.nature.com/articles/s41467-024-48998-4" } });
  sub(s, "Drawbacks reported in the base paper", 6.1, 1.05, 5.3);
  const lims = ["No intrinsic materials knowledge (LLM only plans tools)", "Token-context limits: 4 % of search tasks failed", "Reasoning and logic errors in generated code",
    "Restricted search space (≈100 parent structures)", "Narrow topology coverage (9 topologies)", "One pretrained model needed per property",
    "General, non-fine-tuned LLM (GPT-4)", "High compute cost (GA + simulations)", "Generated / returned results are not validated"];
  lims.forEach((t, i) => T(s, [B(`L${i + 1}  `, { color: H.red }), R(t)], { x: 6.1, y: 1.5 + i * 0.6, w: 5.3, h: 0.5, fontSize: 13 }));

  // ===================================================== 5. Objectives & novelty
  pres.addSection({ title: "Objectives" });
  s = slide("Objectives and Our Novelty", "Objectives", "Six objectives; the table maps each ChatMOF drawback to what MOFChat does.");
  sub(s, "Objectives", 0.4, 1.05, 4.2);
  const objs = ["Exact answers over all 12,020 MOFs with free or local LLMs", "Safe LLM planning: validation, self-correction, fallback", "Multi-objective ranking with NSGA-II",
    "Deep-learning and ML surrogates with uncertainty and SHAP", "Knowledge grounding by retrieval (RAG)", "Measured results: benchmark, held-out set, classification and regression metrics"];
  objs.forEach((t, i) => T(s, [B(`${i + 1}. `, { color: H.navy }), R(t)], { x: 0.4, y: 1.45 + i * 0.85, w: 4.2, h: 0.8, fontSize: 13.5 }));
  table(s, ["Base-paper limitation", "MOFChat novelty"], [
    ["No materials knowledge", "RAG over curated notes + ChatMOF paper"], ["Token limits", "SQL filters first; LLM sees ≤ 10 verified rows"],
    ["Logic errors in code", "LLM writes a JSON plan; validator checks and repairs it"], ["Small search space", "All 12,020 MOFs searched and ranked (NSGA-II)"],
    ["Only 9 topologies", "Every CoRE-MOF structure, 65 metals"], ["One model per property", "Own XGBoost / FT-Transformer surrogates"],
    ["Proprietary GPT-4", "14 free or local LLMs with automatic fallback"], ["High computation", "Millisecond surrogates instead of simulations"],
    ["No validation", "Answer validator + conformal intervals + SHAP + benchmark"]],
  { x: 4.85, y: 1.1, w: 6.55, colW: [2.3, 4.25], rowH: 0.62, fontSize: 12.5 });

  // ===================================================== 6-8. Literature
  pres.addSection({ title: "Literature" });
  const LIT = [
    ["ChatMOF: an AI system for predicting and generating MOFs using LLMs", "Y. Kang, J. Kim", "2024, Nat. Commun. 15, 4705", "GPT-4 agent writes pandas code; MOFTransformer; genetic algorithm", "96.9 / 95.7 / 87.5 % on search / prediction / generation", "Token limits, code errors, answers not checked", "Base paper; we use validated JSON plans + SQL"],
    ["Augmenting LLMs with chemistry tools (ChemCrow)", "A. M. Bran, S. Cox, O. Schilter, C. Baldassari, A. D. White, P. Schwaller", "2024, Nat. Mach. Intell. 6", "GPT-4 + 18 expert tools in a reason-act loop", "Planned real syntheses; found a new chromophore", "Needs GPT-4; tool outputs not cross-checked", "Tool-calling idea; our tools are deterministic and tested"],
    ["MOFDiff: coarse-grained diffusion for MOF design", "X. Fu, T. Xie, A. S. Rosen, T. Jaakkola, J. Smith", "2024, ICLR", "Equivariant diffusion over building blocks + assembly", "Valid, novel MOFs for CO2 capture", "Needs simulation to validate candidates", "Generation is future work for MOFChat"],
    ["TableRAG: million-token table understanding with LMs", "S.-A. Chen, L. Miculicich, J. M. Eisenschlos et al.", "2024, NeurIPS", "Schema and cell retrieval before the LLM", "Scales table QA to huge tables", "Numeric filters still judged by the LLM", "We filter with SQL first; LLM sees ≤ 10 rows"],
    ["Chain-of-Table: evolving tables in the reasoning chain", "Z. Wang, H. Zhang, C.-L. Li et al.", "2024, ICLR", "LLM plans table operations step by step", "State of the art on WikiTQ, TabFact", "No domain validation of operations", "We validate every planned operation"],
    ["Detecting hallucinations in LLMs using semantic entropy", "S. Farquhar, J. Kossen, L. Kuhn, Y. Gal", "2024, Nature 630, 625–630", "Entropy over meanings of sampled answers", "Detects confabulations without task data", "Misses consistent errors; many samples", "We verify answers against data deterministically"],
    ["Harnessing LLMs to collect and analyze MOF property data (L2M3)", "W. Lee, Y. Kang, T. Bae, J. Kim", "2025, JACS 147, 3943–3958", "LLM text mining of > 40,000 articles", "Experimental MOF property database + synthesis recommender", "Extraction errors from text", "Source of real labels for future uptake surrogates"],
    ["MOF-ChemUnity: literature-informed LLMs for MOF research", "T. M. Pruyn, A. Aswad, S. T. Khan, J. Huang, R. Black, S. M. Moosavi", "2025, JACS", "Multi-agent LLM links literature names to CSD structures", "Literature-grounded answers, knowledge graph", "Large infrastructure", "Our RAG grounds answers in notes + ChatMOF paper"],
    ["Accurate predictions on small data with a tabular foundation model (TabPFN)", "N. Hollmann, S. Müller, L. Purucker et al., F. Hutter", "2025, Nature 637, 319–326", "Transformer pretrained on synthetic tables; in-context prediction", "Beats tuned GBDT on ≤ 10k-sample tables", "Limited to ~10k rows / 500 features", "Candidate surrogate for our 8k-row tables"],
    ["TabM: advancing tabular DL with parameter-efficient ensembling", "Y. Gorishniy, A. Kotelnikov, A. Babenko", "2025, ICLR", "MLP + BatchEnsemble", "Beats attention-based tabular DL", "Generic benchmarks", "Supports our finding: FT-Transformer ≈ trees"],
    ["LLaMP: LLM made powerful for materials knowledge retrieval", "Y. Chiang, E. Hsieh, C.-H. Chou, J. Riebesell", "2025, EMNLP (arXiv 2024)", "Hierarchical ReAct agents over Materials Project", "Grounded answers + confidence metric", "Needs Materials Project API", "Same grounding idea for MOFs with a local DB"],
    ["System of agentic AI for the discovery of MOFs (MOFGen)", "T. J. Inizan, S. Yang, …, K. A. Persson, O. M. Yaghi", "2025, arXiv 2504.14110", "LLM proposes compositions; diffusion + quantum-chemistry agents", "Synthesizable MOF candidates", "Heavy compute; preprint", "Agent + verification trend; we verify against the DB"],
    ["L²M³OF: a large language multimodal model for MOFs", "J. Cui, F. Wu, H. Zhao et al.", "2025, arXiv 2510.20976", "Crystal encoder projected into an LLM", "Beats text-only LLMs on property prediction", "Needs structure files + fine-tuning", "We stay tabular; multimodal is future work"],
    ["Conversational LLM agent for synthesis of MOF catalysts (MOFsyn Agent)", "J. Lin et al.", "2025, ACS Nano 19, 23840–23858", "RAG + ML agent guiding synthesis", "Faster Ni@UiO-66(Ce) catalyst optimisation", "Single reaction system", "RAG + ML in a MOF agent, like MOFChat"],
    ["The rise of generative AI for MOF design and synthesis", "C. Duan, A. Nandy, …, S. M. Moosavi, Z. Zheng", "2025, arXiv 2508.13197 (perspective)", "Review of VAEs, diffusion, LLM agents", "Roadmap to closed-loop discovery", "Feasibility and data gaps", "Places MOFChat at the screening stage"],
    ["LitMOF: LLM multi-agent for literature-validated MOF database correction", "H. Kim, D. Kim, J. Kim", "2025, arXiv 2512.01693 (rev. 2026)", "Agents check CSD structures against papers", "189,567 structures; 9,227 entries repaired", "Preprint", "Data quality matters: we audit CoRE-MOF in ETL"],
    ["Enhancing spatial reasoning in LLMs for MOF structure prediction (MOF-LLM)", "M. Pan, J. Li, P. Liu et al.", "2026, arXiv 2601.09285", "Qwen-3 8B with spatial pretraining, SFT and RL", "35.78 % match rate, 0.04 s per structure", "Low match rate", "Small open LLMs can be specialised (cf. our Llama 3 path)"],
    ["An LLM agent for end-to-end computational materials discovery (MAESTRO)", "Y. Chen, J. Huang, Y. Liu et al.", "2026, arXiv 2608.20434", "Agent mines literature, builds DB, screens MOFs", "Finds wet-flue-gas separation candidates", "Preprint", "End-to-end agents; MOFChat is the verified query layer"],
  ];
  for (let p = 0; p < 3; p++) {
    s = slide(`Literature Review (2024–2026) — ${p + 1} / 3`, "Literature",
      p === 0 ? "Eighteen papers from 2024 to 2026, every one checked against its publisher, proceedings or arXiv record. Columns follow the review-1 format: method, contribution, limitation, and how MOFChat uses or addresses it." :
      p === 1 ? "2025 papers: MOF data mining with LLMs, tabular foundation models, grounded materials agents." : "Latest work (2025–2026): agentic MOF discovery and database correction. The gap we fill is a verified, measurable query layer.");
    const rows = LIT.slice(p * 6, p * 6 + 6).map((r, i) => [String(p * 6 + i + 1), { text: r[0], options: { bold: true } }, r[1], r[2], r[3], r[4], r[5], { text: r[6], options: { color: H.navy } }]);
    table(s, ["#", "Paper", "Authors", "Year / Venue", "Method", "Contribution", "Limitation", "Use in MOFChat"], rows,
      { x: 0.25, y: 1.0, w: 11.19, colW: [0.3, 2.0, 1.55, 1.15, 1.6, 1.5, 1.4, 1.69], rowH: [0.4, 1.02, 1.02, 1.02, 1.02, 1.02, 1.02], fontSize: 9, valign: "middle" });
  }

  // ===================================================== 9. Research gap
  s = slide("Research Gap from the Literature", "Literature", "Summarise the four gaps and how MOFChat fills each.");
  const gaps = [["Answers are rarely verified against data", "ChatMOF, ChemCrow, LLaMP trust the LLM's final text; semantic entropy needs many samples.", "Deterministic answer validator: IDs, numbers and comparison claims checked against the database."],
    ["Dependence on proprietary LLMs", "Most agents use GPT-4.", "14 free / local models with fallback; works fully offline (Llama 3)."],
    ["Few honest benchmarks for planning", "Accuracy is reported on the authors' own question sets.", "64-question dev set + 20 held-out phrasings + model comparison + ablation."],
    ["Tabular DL vs trees on MOF descriptors", "TabPFN / TabM / Grinsztajn compare on generic data.", "FT-Transformer vs XGBoost vs GP vs MLP on MOF regression and classification."]];
  table(s, ["Gap", "Evidence in 2024–2026 work", "What MOFChat does"], gaps.map((g) => [{ text: g[0], options: { bold: true } }, g[1], { text: g[2], options: { color: H.navy } }]),
    { x: 0.4, y: 1.2, w: 10.9, colW: [2.7, 3.9, 4.3], rowH: 1.15, fontSize: 13 });

  // ===================================================== 10. Dataset
  pres.addSection({ title: "Dataset" });
  s = slide("Dataset: CoRE MOF 2019 and Preprocessing", "Dataset", "setup_db.py loads the ChatMOF descriptor table and asserts each data-quality fact. The 3,252 zero-area MOFs are physics, not missing data.");
  table(s, ["Category", "Attributes"], [["Identification", "MOF_ID (CSD refcode)"], ["Pore geometry", "LCD, PLD, LFPD (Å)"], ["Density", "Density (g/cm³)"],
    ["Surface area", "Accessible (m²/g, m²/cm³), non-accessible"], ["Porosity", "Void fraction, pore volume, non-accessible volume"], ["Chemistry", "Metal type, open metal site, OMS type"]],
  { x: 0.4, y: 1.1, w: 5.4, colW: [1.5, 3.9], rowH: 0.42, fontSize: 12 });
  T(s, "12,020 experimental MOFs × 17 columns, computed with Zeo++ and a 3.31 Å (N₂) probe.", { x: 0.4, y: 4.3, w: 5.2, h: 0.6, fontSize: 13, italic: true });
  sub(s, "Preprocessing (ETL) findings", 6.0, 1.05, 5.4);
  table(s, ["Check", "Finding → action"], [["Missing values / duplicates", "none"], ["Two column pairs identical", "dropped duplicates"],
    ["Pore volume = void fraction / density", "derived; documented"], ["Zero surface area (3,252)", "all have PLD < 3.31 Å → physics rule"],
    ["Density header said cm³/g", "values are g/cm³ → label fixed"], ["2,087 multi-metal MOFs", "separate mof_metals table"],
    ["Feature scaling", "log1p + z-score (Preprocessor)"]], { x: 6.0, y: 1.45, w: 5.4, colW: [2.6, 2.8], rowH: 0.4, fontSize: 11 });
  await img(s, fig("feat_metals.png"), 0.4, 5.3, 10.9, 2.5);

  // ===================================================== 11-12. Feature extraction
  s = slide("Feature Extraction (1): Descriptor Distributions and Correlations", "Dataset",
    "Ten geometric descriptors feed the models. Distributions are heavy-tailed, so we use log1p + z-score scaling. Strong correlations (surface area with pore volume and void fraction) explain the SHAP results later.");
  await img(s, fig("feat_distributions.png"), 0.3, 1.0, 7.0);
  await img(s, fig("feat_correlation.png"), 7.45, 1.0, 4.0);
  const sc = DL.features.strongest_correlations.slice(0, 4).map(([a, b, c]) => `${a}–${b}: ${c >= 0 ? "+" : ""}${c.toFixed(2)}`);
  sub(s, "What the graphs show", 0.4, 4.0, 6.8);
  bullets(s, ["Most descriptors are right-skewed (log scale) → log1p + z-score normalisation before the FT-Transformer",
    "27 % of MOFs have exactly zero accessible surface area (the spike at 0)", "Strongest correlations: " + sc.join("; "),
    "Pore volume is derived (void fraction / density), so it is excluded when predicting void fraction (no leakage)"], { x: 0.4, y: 4.4, w: 6.9, h: 3.0, fontSize: 13 });
  T(s, "Pearson correlation of the ten descriptors", { x: 7.45, y: 4.45, w: 4.0, h: 0.3, fontSize: 11, italic: true, color: H.grey, align: "center" });

  s = slide("Feature Extraction (2): PCA, Learned Embeddings, Reconstruction", "Dataset",
    "PCA shows the descriptor space is low-dimensional. The FT-Transformer's self-supervised embeddings separate MOFs by surface area and partly by metal. Masked reconstruction shows which descriptors the model can infer from the others.");
  await img(s, fig("feat_pca.png"), 0.3, 1.0, 5.6);
  await img(s, fig("feat_tsne_embeddings.png"), 6.0, 1.0, 5.4);
  await img(s, fig("feat_reconstruction_importance.png"), 0.3, 3.35, 7.0);
  const pe = DL.features.pca_explained;
  bullets(s, [[B("PCA: "), R(`PC1 + PC2 explain ${pct(pe[0] + pe[1], 0)} of the variance of the ten descriptors`)],
    [B("t-SNE of the 64-d FT-Transformer embeddings: "), R("smooth surface-area gradient; metals form local clusters")],
    [B("Masked reconstruction: "), R(`surface area R² ${f3(FTM.reconstruction_r2_masked.Surface_Area)}, void fraction ${f3(FTM.reconstruction_r2_masked.Void_Fraction)} when hidden from the model`)],
    [B("SHAP: "), R("pore volume and void fraction drive surface area; density drives void fraction")]], { x: 7.45, y: 3.45, w: 3.95, h: 4.2, fontSize: 12.5 });

  // ===================================================== 13. Pipeline dashboard -> backend
  pres.addSection({ title: "Architecture" });
  s = slide("Overall Pipeline: from Dashboard to Backend", "Architecture",
    "Follow one question from the Streamlit dashboard through the backend and back. Only the two red boxes use a language model; everything else is deterministic, tested code.");
  T(s, "FRONTEND", { x: 0.3, y: 1.0, w: 2, h: 0.3, fontSize: 12, bold: true, color: H.navy });
  box(s, 0.3, 1.35, 2.2, 0.85, "Streamlit dashboard\n(app.py, 5 pages)", "FAC090");
  box(s, 0.3, 2.45, 2.2, 0.85, "User question\n+ model / planner choice", H.pale.yellow);
  box(s, 0.3, 6.25, 2.2, 1.1, "Answer + verified table\n+ Pareto / SHAP plots\n+ plan / SQL trace", "FAC090");
  arrow(s, 1.4, 2.2, 1.4, 2.45);
  T(s, "BACKEND (mofchat/agent.py orchestrates)", { x: 2.9, y: 1.0, w: 6, h: 0.3, fontSize: 12, bold: true, color: H.navy });
  box(s, 2.95, 2.45, 2.0, 0.85, "LLM planner\nJSON plan (llm.py)", "E6B9B8", { border: H.red });
  box(s, 2.95, 1.35, 2.0, 0.85, "Rule parser\n(rules.py)", H.pale.grey);
  box(s, 5.3, 2.45, 2.0, 0.85, "Plan validator\n(validator.py)", H.pale.aqua);
  box(s, 7.65, 2.45, 1.75, 0.85, "Intent router", H.pale.purple);
  arrow(s, 2.5, 2.87, 2.95, 2.87); arrow(s, 3.95, 2.2, 3.95, 2.45); arrow(s, 4.95, 2.87, 5.3, 2.87); arrow(s, 7.3, 2.87, 7.65, 2.87);
  line(s, 6.3, 2.45, 6.3, 2.32, H.red, 1.5, "dash"); line(s, 4.45, 2.32, 6.3, 2.32, H.red, 1.5, "dash"); arrow(s, 4.45, 2.32, 4.45, 2.45, H.red, 1.5);
  T(s, "errors → retry ≤ 2×", { x: 5.1, y: 2.02, w: 1.8, h: 0.28, fontSize: 10, italic: true, color: H.red });
  box(s, 8.6, 1.35, 2.8, 0.85, "14 LLMs + fallback chain\n(serve the red boxes)", "E6B9B8", { border: H.red, fs: 10 });
  const tools = [["SQL + NSGA-II\n(tools.py, optimizer.py)", H.pale.green], ["FT-Transformer\n+ FAISS similarity", H.pale.blue], ["XGBoost + conformal\n+ SHAP prediction", H.pale.peach], ["RAG: MiniLM +\nFAISS knowledge", H.pale.pink]];
  line(s, 8.52, 3.3, 8.52, 3.65); line(s, 3.9, 3.65, 10.2, 3.65);
  tools.forEach(([t, f], i) => { const x = 2.9 + i * 2.1; arrow(s, x + 1.0, 3.65, x + 1.0, 3.85); box(s, x, 3.85, 2.0, 0.95, t, f, { fs: 10.5 }); line(s, x + 1.0, 4.8, x + 1.0, 5.05); });
  line(s, 3.9, 5.05, 10.2, 5.05);
  const data = [["coremof.db\n(SQLite)", 2.95], ["embeddings.npy\nindex.faiss", 5.15], ["xgb.json, ft.pt\nmeta.json", 7.35], ["knowledge_index\n(104 chunks)", 9.55]];
  arrow(s, 6.1, 5.05, 6.1, 5.3);
  box(s, 4.6, 5.3, 3.0, 0.75, "LLM answer writer (≤ 10 verified rows)", "E6B9B8", { border: H.red, fs: 10.5 });
  arrow(s, 7.6, 5.67, 8.0, 5.67);
  box(s, 8.0, 5.3, 3.4, 0.75, "Answer validator: IDs, numbers, claims", H.pale.aqua, { fs: 10.5 });
  line(s, 9.7, 6.05, 9.7, 6.8); arrow(s, 9.7, 6.8, 2.5, 6.8);
  T(s, "STORED ARTIFACTS:", { x: 2.95, y: 6.25, w: 2.2, h: 0.3, fontSize: 10, bold: true, color: H.grey });
  data.forEach(([t, x]) => T(s, t, { x: x + 0.05, y: 6.95, w: 2.0, h: 0.6, fontSize: 9.5, color: H.grey, align: "center", fontFace: "Courier New" }));
  T(s, "red = uses a language model; other boxes = deterministic, unit-tested code", { x: 2.95, y: 7.65, w: 7.5, h: 0.3, fontSize: 10.5, italic: true, color: H.grey });

  // ===================================================== 14. Offline + online pipeline
  s = slide("Pipeline Architecture: Offline Training and Online Inference", "Architecture",
    "Offline scripts build every artifact once; the online pipeline only loads them. evaluate.py and evaluate_dl.py produce all the numbers in this deck.");
  sub(s, "Offline (run once)", 0.4, 1.0, 5);
  const off = [["MOF dataset\n(CoRE MOF 2019)", "8064A2", "FFFFFF"], ["setup_db.py\nETL + checks", H.pale.green], ["Feature scaling\nlog1p + z-score", H.pale.aqua],
    ["train_ft.py\nmasked FT-Transformer", H.pale.peach], ["train_property_\nmodels.py\nXGBoost, GP, Ridge, FT", H.pale.blue], ["setup_vectorstore.py\nMiniLM + FAISS", H.pale.pink],
    ["evaluate.py / evaluate_dl.py\nmetrics + figures", H.pale.yellow]];
  off.forEach(([t, f, c], i) => { const x = 0.35 + i * 1.6; box(s, x, 1.45, 1.45, 1.15, t, f, { fs: 8.5, color: c || "000000" }); if (i < off.length - 1) arrow(s, x + 1.45, 2.02, x + 1.6, 2.02); });
  sub(s, "Online (per question)", 0.4, 3.0, 5);
  const on = [["User query\n(dashboard)", "FAC090"], ["Plan\nLLM + rules", "E6B9B8"], ["Validate\nplan", H.pale.aqua], ["Execute\nSQL / NSGA-II /\nFT / XGB / RAG", H.pale.green],
    ["Write answer\n(LLM)", "E6B9B8"], ["Validate answer", H.pale.aqua], ["Show answer\n+ evidence", "FAC090"]];
  on.forEach(([t, f], i) => { const x = 0.35 + i * 1.6; box(s, x, 3.45, 1.45, 1.15, t, f, { fs: 10 }); if (i < on.length - 1) arrow(s, x + 1.45, 4.02, x + 1.6, 4.02); });
  sub(s, "Feature-extraction path inside the FT-Transformer", 0.4, 5.0, 8);
  const fe = [["10 descriptors\n+ metal, OMS", H.pale.grey], ["Feature tokenizer\nx·Wⱼ + bⱼ", H.pale.aqua], ["[CLS] + 3 Transformer\nblocks (d = 64)", H.pale.blue],
    ["64-d MOF\nembedding", H.pale.peach], ["FAISS cosine\nnearest neighbours", H.pale.green], ["“MOFs similar\nto X”", "FAC090"]];
  fe.forEach(([t, f], i) => { const x = 0.35 + i * 1.87; box(s, x, 5.45, 1.7, 1.0, t, f, { fs: 10 }); if (i < fe.length - 1) arrow(s, x + 1.7, 5.95, x + 1.87, 5.95); });
  T(s, "Review-1 used 384-d embeddings matched to a Sentence-BERT question vector; the two were never trained together, so that path was replaced by plan → validate → SQL (9.4 % → 100 % exact answers).",
    { x: 0.4, y: 6.7, w: 10.9, h: 0.75, fontSize: 12, italic: true, color: H.grey });

  // ===================================================== 15. Models used
  s = slide("Models and Embedded Models Used", "Architecture",
    "Every model in the system, its type and its job. Language models plan and write; embedding models turn text or MOFs into vectors; ML models predict and classify; algorithms rank and explain.");
  table(s, ["Model / tool", "Type", "Role in MOFChat"], [
    [{ text: "Gemini 3.1 Flash-Lite (default)", options: { bold: true } }, "LLM, cloud (free)", "Planner (JSON plan) and answer writer"],
    [{ text: "GPT-OSS 120B / 20B, Qwen 3.8 27B (Groq)", options: { bold: true } }, "LLMs, cloud (free)", "Fallback planners / writers"],
    [{ text: "Nemotron 3, Gemma 4 (OpenRouter)", options: { bold: true } }, "LLMs, cloud (free)", "Further fallbacks"],
    [{ text: "Llama 3 / 3.1 8B, Qwen 2.5 7B, Nemotron Mini (Ollama)", options: { bold: true } }, "LLMs, local", "Fully offline planning and answers"],
    [{ text: "all-MiniLM-L6-v2 (Sentence-BERT)", options: { bold: true } }, "Embedding model, 384-d", "Embeds questions + knowledge chunks for RAG"],
    [{ text: `FT-Transformer, masked autoencoder (${(FTM.n_params / 1000).toFixed(0)}k params)`, options: { bold: true } }, "Embedding model, 64-d (DL)", "MOF embeddings for similarity search"],
    [{ text: "FT-Transformer regressor / classifier", options: { bold: true } }, "Deep learning", "Surface area, void fraction; open-metal-site classification"],
    [{ text: "MLP classifier", options: { bold: true } }, "Deep learning", "Baseline for open-metal-site classification"],
    [{ text: "XGBoost", options: { bold: true } }, "Gradient-boosted trees", "Main surrogate (+ SHAP, conformal); OMS classifier"],
    [{ text: "Gaussian process, Ridge, Logistic regression", options: { bold: true } }, "Classical ML", "Baselines; GP gives 95 % intervals"],
    [{ text: "FAISS", options: { bold: true } }, "Vector index", "Fast cosine nearest-neighbour search"],
    [{ text: "NSGA-II", options: { bold: true } }, "Multi-objective algorithm", "Pareto ranking of candidate MOFs"],
    [{ text: "SHAP (TreeSHAP), split-conformal", options: { bold: true } }, "Explainability / uncertainty", "Feature contributions; 90 % prediction intervals"],
    [{ text: "SQLite, Streamlit, PyTorch, LangChain", options: { bold: true } }, "Infrastructure", "Database, dashboard, DL framework, LLM clients"]],
  { x: 0.3, y: 1.0, w: 11.1, colW: [4.4, 2.6, 4.1], rowH: 0.44, fontSize: 11 });

  // ===================================================== 16. Model architecture FT
  s = slide("Model Architecture: FT-Transformer (Gorishniy et al., 2021)", "Architecture",
    "One backbone, three heads. Each descriptor becomes a token; a [CLS] token summarises them through three pre-norm Transformer blocks. The self-supervised head masks 30 % of tokens; the regression and classification heads are trained separately.");
  const toks = ["[CLS]", "LCD", "PLD", "LFPD", "Density", "SA", "ASA_vol", "VF", "PV", "NASA", "NAV", "metal"];
  toks.forEach((t, i) => box(s, 0.35 + i * 0.6, 6.7, 0.55, 0.55, t, i === 0 ? "E6B9B8" : i === 11 ? H.pale.purple : H.pale.aqua, { fs: 7.5 }));
  T(s, "Input tokens: numeric xⱼ·Wⱼ + bⱼ, categorical embedding, learned [CLS]; 30 % of numeric tokens replaced by [MASK] during self-supervised training",
    { x: 0.35, y: 7.35, w: 7.2, h: 0.5, fontSize: 10, italic: true, color: H.grey });
  arrow(s, 3.9, 6.7, 3.9, 6.35);
  box(s, 0.6, 3.3, 6.6, 3.05, "", H.pale.blue);
  T(s, "× 3 pre-norm Transformer blocks  (d_token = 64, 4 heads, FFN × 2, dropout 0.1)", { x: 0.8, y: 3.35, w: 6.2, h: 0.35, fontSize: 12, bold: true, align: "center" });
  ["LayerNorm", "Multi-head self-attention", "+ residual", "LayerNorm", "Feed-forward (ReLU)", "+ residual"].forEach((t, i) =>
    box(s, 1.2 + (i % 3) * 1.85, 3.85 + Math.floor(i / 3) * 1.15, 1.7, 0.8, t, i === 1 ? "FAC090" : "FFFFFF", { fs: 10.5 }));
  arrow(s, 3.9, 3.3, 3.9, 2.95);
  box(s, 2.6, 2.35, 2.6, 0.6, "LayerNorm → [CLS] (64-d)", H.pale.peach, { fs: 11 });
  [["Masked decoder → 10 descriptors\n(self-supervised, MSE)", 0.35], ["Linear → 1 value\n(regression, MSE)", 2.75], ["Linear → logit\n(OMS classifier, BCE)", 5.15]].forEach(([t, x]) => {
    arrow(s, 3.9, 2.35, x + 1.15, 1.9); box(s, x, 1.05, 2.3, 0.85, t, H.pale.green, { fs: 10.5 });
  });
  sub(s, "Configuration", 7.7, 1.05, 3.6, H.navy);
  table(s, ["Item", "Value"], [["Parameters (embedding)", `${FTM.n_params.toLocaleString()}`], ["Parameters (classifier)", DL.oms.ft_params.toLocaleString()],
    ["Blocks / heads / d", "3 / 4 / 64"], ["Optimiser", "AdamW, lr 1e-3, wd 1e-5"], ["Batch / early stopping", "256 / val loss"], ["SSL masking", "30 % of tokens"],
    ["SSL training", `${FTM.epochs_trained} epochs`], ["Regressor (SA)", `${PM.Surface_Area.ft_epochs} epochs`], ["Classifier (OMS)", `best epoch ${DL.oms.history["FT-Transformer"].best_epoch}`]],
  { x: 7.7, y: 1.45, w: 3.7, colW: [1.9, 1.8], rowH: 0.4, fontSize: 10.5 });
  T(s, "Embedding → FAISS similarity. Regression → surface area / void fraction. Classification → open metal site.", { x: 7.7, y: 6.2, w: 3.7, h: 1.0, fontSize: 12, color: H.navy });

  // ===================================================== 17. Planner + validator
  s = slide("LLM Planning Architecture: Plan, Validate, Execute", "Architecture",
    "Real plan for the demo question. The LLM fills a fixed JSON schema at temperature 0 with nine few-shot examples. The validator checks it and sends errors back up to twice; the hybrid planner adds facts the rule parser is certain about.");
  box(s, 0.4, 1.1, 5.6, 0.6, "“Which zinc MOFs have high surface area and low density?”", H.pale.yellow, { fs: 12.5, bold: false });
  arrow(s, 3.2, 1.7, 3.2, 1.95);
  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 1.95, w: 5.6, h: 2.05, fill: { color: "1F2A36" }, line: { color: "1F2A36", width: 0 } });
  T(s, '{ "intent": "search",\n  "metals": ["Zn"],\n  "objectives": [\n    {"column": "Surface_Area", "direction": "max"},\n    {"column": "Density", "direction": "min"} ],\n  "limit": 5 }',
    { x: 0.6, y: 2.05, w: 5.3, h: 1.9, fontSize: 11.5, fontFace: "Courier New", color: "E7EEF4" });
  arrow(s, 3.2, 4.0, 3.2, 4.25);
  box(s, 0.4, 4.25, 5.6, 1.05, "Executor: whitelisted columns, bound parameters, read-only SQL\nSELECT * FROM materials WHERE MOF_ID IN (SELECT MOF_ID FROM mof_metals WHERE Metal IN (?))\n→ 2 objectives → NSGA-II Pareto ranking", H.pale.green, { fs: 10, bold: false });
  T(s, "Intents classified by the planner: search · count · lookup · similar · predict · knowledge · out_of_scope", { x: 0.4, y: 5.5, w: 5.6, h: 0.6, fontSize: 12, color: H.navy });
  sub(s, "Validator checks", 6.4, 1.05, 5);
  bullets(s, ["Column aliases resolved from one registry", "Units, operators and percentages normalised", "Impossible or invented values rejected",
    "Thresholds not in the question → preferences", "MOF IDs not in the question dropped", "Superlatives written as constraints repaired",
    "Application presets expanded (H₂, CH₄, CO₂, sieving, catalysis)", "Objectives not asked for in an application question dropped"], { x: 6.4, y: 1.45, w: 5.0, h: 4.4, fontSize: 13 });
  T(s, "Fallback: if errors remain after 2 corrections, the rule-parser plan is used; if no LLM is reachable, rules + template answer.", { x: 6.4, y: 6.0, w: 5.0, h: 0.8, fontSize: 12, italic: true, color: H.grey });

  // ===================================================== 18. NSGA-II
  s = slide("Multi-Objective Ranking with NSGA-II", "Architecture",
    "Real data for the hydrogen-storage preset: grey = candidates, blue = Pareto fronts 2-3, red = front 1. NSGA-II's selection step is non-dominated sorting plus crowding distance.");
  const P = JSON.parse(fs.readFileSync(path.join(HERE, "pareto.json")));
  const xs = [...P.bg.map((p) => p[0]), ...P.f23.map((p) => p[0]), ...P.f1.map((p) => p[0])];
  const nb = P.bg.length, n2 = P.f23.length, n1 = P.f1.length;
  const pad = (arr, a, b) => [...Array(a).fill(null), ...arr, ...Array(b).fill(null)];
  s.addChart(pres.charts.SCATTER, [{ name: "X", values: xs }, { name: "Candidates (sample of 700)", values: pad(P.bg.map((p) => p[1]), 0, n2 + n1) },
    { name: "Pareto fronts 2–3", values: pad(P.f23.map((p) => p[1]), nb, n1) }, { name: "Front 1 (recommended)", values: pad(P.f1.map((p) => p[1]), nb + n2, 0) }], {
    x: 5.6, y: 1.0, w: 5.9, h: 5.4, lineSize: 0, lineDataSymbol: "circle", lineDataSymbolSize: 6, chartColors: ["BFBFBF", H.blue, H.red],
    showLegend: true, legendPos: "b", legendFontSize: 11, legendFontFace: "Arial", showTitle: true, title: "H₂ storage: 10,226 MOFs with PLD ≥ 2.89 Å",
    titleFontSize: 13, titleFontFace: "Arial", showValAxisTitle: true, valAxisTitle: "Void fraction", showCatAxisTitle: true, catAxisTitle: "Surface area (m²/g)",
    valAxisTitleFontSize: 11, catAxisTitleFontSize: 11, valAxisTitleFontFace: "Arial", catAxisTitleFontFace: "Arial", valAxisMinVal: 0, valAxisMaxVal: 1,
    catAxisMinVal: 0, catAxisMaxVal: 9000, catAxisLabelFontSize: 10, valAxisLabelFontSize: 10, catAxisLabelFontFace: "Arial", valAxisLabelFontFace: "Arial",
    valGridLine: { color: "E0E0E0", size: 0.5 }, catGridLine: { style: "none" }, valAxisLabelFormatCode: "0.0" });
  bullets(s, [[B("Domination: "), R("A beats B if A is at least as good on every objective and better on one")], [B("Non-dominated sorting: "), R("front 1 = MOFs nobody beats; remove; repeat")],
    [B("Crowding distance: "), R("prefers MOFs in sparse regions → diverse trade-offs")], [B("Exact O(n log n) sweep "), R("for two objectives; worst 25 % screened out first")],
    [B("Speed: "), R("all 12,020 MOFs in 0.02 s (2 objectives), 2.6 s (3)")]], { x: 0.4, y: 1.1, w: 5.0, h: 3.4, fontSize: 13 });
  table(s, ["Application preset", "Rule (heuristic)"], [["H₂ storage", "PLD ≥ 2.89 Å; max surface area, void fraction"], ["CH₄ storage", "PLD ≥ 3.80 Å; max volumetric area, void fraction"],
    ["CO₂ capture", "open metal site; PLD ≥ 3.30 Å; min LCD"], ["Separation A/B", "d_A ≤ PLD ≤ d_B (kinetic diameters)"], ["Catalysis", "open metal site; PLD ≥ 5 Å"]],
  { x: 0.4, y: 4.75, w: 5.0, colW: [1.5, 3.5], rowH: 0.42, fontSize: 11 });

  // ===================================================== 19. Benchmark
  pres.addSection({ title: "Results" });
  const sys = SUM.benchmark.systems, ho = SUM.heldout.systems;
  const names = ["Review-1 two-tower (shipped)", "Rules planner (no LLM)", "LLM planner, single shot (no validator)", "LLM planner + validator", "Hybrid (default)"];
  const short = ["Review-1 two-tower", "Rules only", "LLM single shot", "LLM + validator", "Hybrid (default)"];
  s = slide("Results (1): Retrieval Benchmark — Exact Answers, 5 % → 100 %", "Results",
    "A system is correct only if it returns exactly the gold MOFs. The held-out set (20 phrasings written after tuning) is the honest estimate. Review 1 gets 5 %, the default hybrid 100 %. The ablation on the right shows the validator and hybrid add 15 points for the offline model.");
  s.addChart(pres.charts.BAR, [{ name: "Development (64 questions)", labels: short, values: names.map((n) => sys[n].result_accuracy) },
    { name: "Held-out (20 questions)", labels: short, values: names.map((n) => ho[n].result_accuracy) }], {
    x: 0.3, y: 1.0, w: 6.5, h: 4.6, barDir: "col", barGapWidthPct: 60, chartColors: ["A6A6A6", H.blue], showValue: true, dataLabelPosition: "outEnd",
    dataLabelFontSize: 10, dataLabelFontFace: "Arial", dataLabelFormatCode: "General\"%\"", showLegend: true, legendPos: "t", legendFontSize: 11, legendFontFace: "Arial",
    showTitle: true, title: "Exact answer match (%), LLM = Gemini 3.1 Flash-Lite", titleFontSize: 13, titleFontFace: "Arial", valAxisMaxVal: 115, valAxisMinVal: 0,
    valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, catAxisLabelFontSize: 10, catAxisLabelFontFace: "Arial" });
  s.addChart(pres.charts.BAR, [{ name: "Held-out", labels: ["Llama 3 alone", "+ validator", "+ hybrid"], values: [65, 70, 80] },
    { name: "Development", labels: ["Llama 3 alone", "+ validator", "+ hybrid"], values: [85.9, 93.8, 100] }], {
    x: 7.0, y: 1.0, w: 4.4, h: 4.6, barDir: "col", barGapWidthPct: 60, chartColors: [H.red, "A6A6A6"], showValue: true, dataLabelPosition: "outEnd",
    dataLabelFontSize: 10, dataLabelFontFace: "Arial", dataLabelFormatCode: "General\"%\"", showLegend: true, legendPos: "t", legendFontSize: 11, legendFontFace: "Arial",
    showTitle: true, title: "Ablation: offline Llama 3 8B", titleFontSize: 13, titleFontFace: "Arial", valAxisMaxVal: 115, valAxisMinVal: 0, valAxisHidden: true,
    valGridLine: { style: "none" }, catGridLine: { style: "none" }, catAxisLabelFontSize: 10, catAxisLabelFontFace: "Arial" });
  bullets(s, [[B("Exact = "), R("same MOFs (or count) as a hand-written gold plan; constraint precision@k on held-out: review-1 " + ho[names[0]].constraint_precision_at_k + " %, hybrid " + ho[names[4]].constraint_precision_at_k + " %")],
    [B("Dev 100 % is optimistic "), R("for rules (tuned on it); held-out phrasings were never used for tuning")],
    [B("Validator + hybrid add +15 points offline "), R("for < 0.01 s; with a strong cloud model they change nothing (insurance)")],
    [B("ChatMOF "), R("reports 96.9 % on its own search set (different questions, not directly comparable)")]], { x: 0.4, y: 5.85, w: 11.0, h: 1.9, fontSize: 12.5 });

  // ===================================================== 20. Model comparison + answer validation
  s = slide("Results (2): Free-LLM Comparison and Answer Validation", "Results",
    "Each model planned both sets alone with fallback off. Cloud models tie on accuracy; reliability and speed differ. The answer validator caught invented numbers, a garbled ID and a false Pareto claim.");
  table(s, ["Model", "Held-out alone", "Held-out hybrid", "Dev hybrid", "Median call", "Provider errors"], [
    [{ text: "Gemini 3.1 Flash-Lite (default)", options: { bold: true } }, "100 %", "100 %", "100 %", "1.5 s", "13 / 84"], ["GPT-OSS 120B (Groq)", "95 %", "95 %", "100 %", "2.4–4.7 s", "0"],
    ["Qwen 3.8 27B (Groq)", "95 %", "95 %", "100 %", "20 s", "0"], ["Nemotron 3 Super 120B", "95 %", "95 %", "–", "2.0 s", "0"], ["Llama 3 8B (local)", "65 %", "80 %", "100 %", "1.5 s", "0"],
    ["Gemini 3.5 Flash", "–", "–", "–", "–", "64 / 84 (quota)"]], { x: 0.3, y: 1.05, w: 11.1, colW: [3.4, 1.5, 1.5, 1.3, 1.5, 1.9], rowH: 0.42, fontSize: 12, align: "center" });
  sub(s, "Answer validation (16 full answers per model)", 0.4, 4.15, 6);
  table(s, ["Model", "Drafts with a problem", "Rewritten", "Still flagged", "s / answer"], [["Gemini 3.1 Flash-Lite", "0 of 16", "0", "0", "9.9"],
    ["Llama 3 8B (local)", "2 of 16", "1", "0", "9.3"], ["GPT-OSS 120B", "2 of 16", "2", "1", "30.2"], ["Qwen 3.8 27B", "0 of 16", "0", "0", "26.4"]],
  { x: 0.3, y: 4.55, w: 6.6, colW: [2.2, 1.4, 1.0, 1.1, 0.9], rowH: 0.42, fontSize: 11.5, align: "center" });
  sub(s, "What the validator caught", 7.2, 4.15, 4.2);
  bullets(s, ["Llama 3: invented two densities and “90 %”; ID OFEUN06 → OFERUN06 auto-corrected", "GPT-OSS 120B: claimed “Pareto front 1”; NSGA-II rank was 2 → flagged",
    "Llama 3 (prediction): invented MOF names (“MOF-210”) → now flagged", "GPT-OSS: cited a prompt header “[WHY]” → now stripped"], { x: 7.2, y: 4.55, w: 4.2, h: 3.2, fontSize: 12 });

  // ===================================================== 21. DL classification metrics + ROC
  const om = DL.oms.models;
  const order = ["Majority baseline", "Logistic regression", "XGBoost", "MLP", "FT-Transformer"];
  const best = order.slice(1).reduce((a, b) => (om[b].roc_auc > om[a].roc_auc ? b : a));
  s = slide("Results (3): Classification — Open-Metal-Site Prediction (DL vs ML)", "Results",
    `Task: predict whether a MOF has an open metal site from its 10 geometric descriptors and primary metal (OMS_Type excluded to avoid leakage). ${pct(DL.oms.positive_rate, 0)} of MOFs have one, so the majority baseline is ${pct(om["Majority baseline"].accuracy)}. Stratified 70/15/15 split; metrics on the untouched test set. Best ROC-AUC: ${best}.`);
  table(s, ["Model", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC", "PR-AUC"], order.map((n) => [{ text: n, options: { bold: true, color: n === best ? H.red : "000000" } },
    f3(om[n].accuracy), f3(om[n].precision), f3(om[n].recall), f3(om[n].f1), f3(om[n].roc_auc), f3(om[n].pr_auc)]),
  { x: 0.3, y: 1.05, w: 11.1, colW: [3.0, 1.35, 1.35, 1.35, 1.35, 1.35, 1.35], rowH: 0.4, fontSize: 12, align: "center" });
  await img(s, fig("oms_roc_pr.png"), 0.3, 3.65, 8.4, 4.1);
  T(s, [B("Why this task: ", { color: H.navy }), R("an open metal site is required by the CO₂-capture preset; predicting it from geometry lets MOFChat screen descriptor sets that are not in the database.")],
    { x: 8.85, y: 3.75, w: 2.6, h: 2.2, fontSize: 11.5 });
  T(s, [B("Split: ", { color: H.navy }), R(`${DL.oms.split.train} / ${DL.oms.split.val} / ${DL.oms.split.test} MOFs (train / val / test)`)], { x: 8.85, y: 6.05, w: 2.6, h: 0.9, fontSize: 11.5 });

  // ===================================================== 22. Confusion matrices
  s = slide("Results (4): Confusion Matrices of the OMS Classifiers (Test Set)", "Results",
    "Rows are the true class, columns the prediction. Read off false positives (predicted OMS, none present) and false negatives.");
  await img(s, fig("oms_confusion.png"), 0.3, 1.05, 11.1);
  const cmTxt = ["XGBoost", "MLP", "FT-Transformer"].map((n) => { const [[tn, fp], [fn, tp]] = om[n].confusion; return [n, tn, fp, fn, tp]; });
  table(s, ["Model", "True negative", "False positive", "False negative", "True positive", "Train / val / test accuracy"],
    cmTxt.map(([n, tn, fp, fn, tp]) => [{ text: n, options: { bold: true } }, String(tn), String(fp), String(fn), String(tp), om[n].acc_train_val_test.map(f3).join(" / ")]),
  { x: 0.3, y: 4.25, w: 11.1, colW: [2.4, 1.6, 1.6, 1.6, 1.6, 2.3], rowH: 0.42, fontSize: 12, align: "center" });
  bullets(s, [`All learned classifiers beat the majority baseline (${pct(om["Majority baseline"].accuracy)} accuracy, ROC-AUC 0.50); XGBoost is best, the two deep models are close behind`,
    "Train vs test accuracy shows how much each model overfits; early stopping on validation loss controls it for the deep models",
    "Our reading: whether a metal site is open depends on coordination chemistry that pore geometry and metal type only partly capture, so accuracy levels off near 75 %"], { x: 0.4, y: 6.15, w: 11.0, h: 1.6, fontSize: 12.5 });

  // ===================================================== 23. Learning curves classification
  s = slide("Results (5): Train / Validation / Test Accuracy and Loss Curves", "Results",
    "Top row: binary cross-entropy loss; bottom row: accuracy. Blue = train, red = validation, green dashed = final test accuracy, dotted line = best (early-stopping) epoch.");
  await img(s, fig("oms_learning_curves.png"), 0.4, 1.0, 10.9, 6.35);
  const hFT = DL.oms.history["FT-Transformer"];
  T(s, `FT-Transformer: best epoch ${hFT.best_epoch} of ${hFT.val_loss.length} · MLP: best epoch ${DL.oms.history.MLP.best_epoch} · XGBoost: best round ${DL.oms.history.XGBoost.best_epoch}. Validation loss rising after the dotted line = overfitting, which early stopping avoids.`,
    { x: 0.4, y: 7.4, w: 10.9, h: 0.45, fontSize: 11.5, italic: true, color: H.grey });

  // ===================================================== 24. Regression prediction
  s = slide("Results (6): Property Prediction (Regression)", "Results",
    "XGBoost is the production surrogate: R² 0.982 on surface area. The FT-Transformer ties it, as the tabular-DL literature predicts. The conformal interval covers 90.5 % of test MOFs.");
  const regModels = ["Mean baseline", "Ridge", "Gaussian Process", "XGBoost", "FT-Transformer"];
  s.addChart(pres.charts.BAR, [{ name: "Surface area", labels: regModels, values: regModels.map((m) => Math.max(0, PM.Surface_Area.models[m].test_all.R2)) },
    { name: "Void fraction", labels: regModels, values: regModels.map((m) => Math.max(0, PM.Void_Fraction.models[m].test_all.R2)) }], {
    x: 0.3, y: 1.0, w: 5.4, h: 3.6, barDir: "bar", barGapWidthPct: 50, chartColors: [H.blue, "A6A6A6"], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 9,
    dataLabelFontFace: "Arial", dataLabelFormatCode: "0.000", showLegend: true, legendPos: "b", legendFontSize: 10, legendFontFace: "Arial", showTitle: true,
    title: "Test R² (held-out 10 %)", titleFontSize: 12, titleFontFace: "Arial", valAxisMaxVal: 1.15, valAxisMinVal: 0, valAxisHidden: true, valGridLine: { style: "none" },
    catGridLine: { style: "none" }, catAxisOrientation: "maxMin", catAxisLabelFontSize: 10, catAxisLabelFontFace: "Arial" });
  await img(s, path.join(HERE, "parity_xgb_ft.png"), 5.9, 1.05, 5.5);
  T(s, "Predicted vs actual surface area on test MOFs", { x: 5.9, y: 3.85, w: 5.5, h: 0.3, fontSize: 11, italic: true, color: H.grey, align: "center" });
  const sa = PM.Surface_Area, vf = PM.Void_Fraction, rg = DL.regression;
  const xs3 = (t) => ["train", "val", "test"].map((k) => f3(rg[t].xgb_production_split_metrics[k].R2)).join(" / ");
  table(s, ["Target", "XGBoost MAE", "XGBoost R² train / val / test*", "FT R² train / val / test*", "90 % conformal coverage", "GP 95 % coverage"], [
    [{ text: "Surface area (m²/g)", options: { bold: true } }, sa.models.XGBoost.test_all.MAE.toFixed(1), xs3("Surface_Area"),
      [rg.Surface_Area.ft_final.train_r2, rg.Surface_Area.ft_final.val_r2, rg.Surface_Area.ft_final.test_r2_accessible].map(f3).join(" / "), pct(sa.conformal.test_coverage), pct(sa.gpr.coverage_95)],
    [{ text: "Void fraction", options: { bold: true } }, vf.models.XGBoost.test_all.MAE.toFixed(3), xs3("Void_Fraction"),
      [rg.Void_Fraction.ft_final.train_r2, rg.Void_Fraction.ft_final.val_r2, rg.Void_Fraction.ft_final.test_r2_accessible].map(f3).join(" / "), pct(vf.conformal.test_coverage), pct(vf.gpr.coverage_95)]],
  { x: 0.3, y: 4.85, w: 11.1, colW: [2.0, 1.3, 2.5, 2.5, 1.5, 1.3], rowH: 0.45, fontSize: 11.5, align: "center" });
  T(s, `* R² on MOFs with accessible pores (the physics rule handles the zeros exactly; it is ${pct(sa.hurdle.rule_accuracy_test)} accurate on test). XGBoost trains in ${sa.train_seconds.XGBoost} s vs ${sa.train_seconds["FT-Transformer"]} s for the FT-Transformer.`,
    { x: 0.3, y: 6.55, w: 11.1, h: 0.6, fontSize: 11.5, italic: true, color: H.grey });
  T(s, "Prediction card in the app: value ± conformal interval, FT-Transformer second opinion, SHAP drivers.", { x: 0.3, y: 7.25, w: 11.1, h: 0.4, fontSize: 12.5, color: H.navy, bold: true });

  // ===================================================== 25. Regression learning curves
  s = slide("Results (7): Regression Learning Curves — Train vs Validation", "Results",
    "FT-Transformer loss and R² per epoch, and XGBoost RMSE per boosting round, for both targets. Validation curves flatten where early stopping picks the model; the dashed green line is the test R².");
  await img(s, fig("regression_learning_curves.png"), 0.4, 1.0, 10.9, 6.35);
  T(s, `FT-Transformer best epoch: surface area ${rg.Surface_Area.ft_best_epoch}, void fraction ${rg.Void_Fraction.ft_best_epoch}. XGBoost best round: ${rg.Surface_Area.xgb_best_round} and ${rg.Void_Fraction.xgb_best_round}.`,
    { x: 0.4, y: 7.4, w: 10.9, h: 0.45, fontSize: 11.5, italic: true, color: H.grey });

  // ===================================================== 26. Intent + off-topic classification
  const it = DL.intent, ot = DL.offtopic;
  s = slide("Results (8): Intent Classification and Off-Topic Detection", "Results",
    "The planner is a 7-class intent classifier; the knowledge retriever is a binary in-domain / off-topic classifier. Both evaluated on saved benchmark outputs (no new LLM calls) and fixed thresholds.");
  await img(s, fig("intent_confusion.png"), 0.3, 1.0, 11.1, 3.65);
  await img(s, fig("offtopic_roc.png"), 0.3, 4.7, 8.0, 2.4);
  const iRows = ["Rules planner (no LLM)", "Llama 3 8B (local), alone", "Llama 3 8B (local), hybrid", "Gemini 3.1 Flash-Lite, hybrid"];
  table(s, ["Planner", "Intent acc.", "Macro F1"], iRows.map((n) => [n.replace(" (local)", "").replace("Gemini 3.1 ", ""), f3(it[n].accuracy), f3(it[n].macro_f1)]),
    { x: 8.45, y: 4.75, w: 3.0, colW: [1.6, 0.7, 0.7], rowH: 0.36, fontSize: 9.5, align: "center" });
  T(s, `Off-topic detector: ROC-AUC ${f3(ot.roc_auc)}, accuracy ${f3(ot.accuracy)} on ${ot.n_in_domain} MOF vs ${ot.n_off_topic} off-topic questions (threshold ${ot.threshold}, fixed beforehand).`,
    { x: 0.3, y: 7.2, w: 11.1, h: 0.55, fontSize: 11.5, italic: true, color: H.grey });

  // ===================================================== 27. Explainability + similarity
  s = slide("Results (9): Explainability and Similarity Search", "Results",
    "SHAP for the surface-area surrogate is physically sensible. The FT-Transformer attention shows which descriptors the deep model uses for OMS classification. Embedding neighbours are nearly as close as raw k-NN but share the metal more often.");
  await img(s, path.join(PROJ, "artifacts/property_models/shap_summary_Surface_Area.png"), 0.3, 1.0, 5.6);
  await img(s, fig("oms_ft_attention.png"), 6.1, 1.0, 5.3);
  const simm = FTM.similarity;
  table(s, ["Neighbours from (1,000 queries × 10)", "Descriptor gap (σ)", "Same metal", "Same OMS flag"], [
    [{ text: "FT-Transformer embedding", options: { bold: true } }, f3(simm.ft_embedding.mean_abs_descriptor_diff_std), pct(simm.ft_embedding.same_metal_rate), pct(simm.ft_embedding.same_open_metal_site_rate)],
    ["k-NN on raw descriptors", f3(simm.raw_descriptor_knn.mean_abs_descriptor_diff_std), pct(simm.raw_descriptor_knn.same_metal_rate), pct(simm.raw_descriptor_knn.same_open_metal_site_rate)],
    ["Random MOFs", f3(simm.random.mean_abs_descriptor_diff_std), pct(simm.random.same_metal_rate), pct(simm.random.same_open_metal_site_rate)]],
  { x: 0.3, y: 4.45, w: 6.9, colW: [2.9, 1.4, 1.2, 1.4], rowH: 0.42, fontSize: 11.5, align: "center" });
  bullets(s, ["Pore volume and void fraction dominate surface-area predictions; density dominates void fraction", "Knowledge retrieval: hit@1 75 %, hit@3 83 %",
    "Every prediction in the app shows its SHAP drivers and a 90 % interval"], { x: 7.45, y: 4.5, w: 3.95, h: 2.8, fontSize: 12.5 });

  // ===================================================== 28. Limitations addressed
  s = slide("Results (10): ChatMOF Limitations Addressed", "Results", "Seven of nine limitations fully addressed; two partly. Be upfront about generation and gas uptake.");
  table(s, ["ChatMOF limitation", "What MOFChat does", "Status"], [["No intrinsic knowledge", "RAG over curated notes + ChatMOF paper", "Done"],
    ["Token-context limits", "SQL first; LLM sees ≤ 10 rows", "Done"], ["Logic errors in LLM code", "JSON plan, validator, whitelisted SQL", "Done"],
    ["Restricted search space", "All 12,020 MOFs searched and ranked", "Done"], ["Narrow topology coverage", "All CoRE-MOF structures, 65 metals", "Done*"],
    ["Pretrained model per property", "Own surrogates + OMS classifier trained on the table", "Done*"], ["General, non-fine-tuned LLM", "Domain prompts, few-shot, presets", "Partly"],
    ["High compute cost", "Millisecond screening; XGBoost trains in 0.25 s", "Done"], ["Unvalidated output", "Answer validator, intervals, SHAP, benchmark", "Done"]].map((r) =>
    [{ text: r[0], options: { bold: true } }, r[1], { text: r[2], options: { bold: true, color: r[2] === "Partly" ? H.red : H.navy, align: "center" } }]),
  { x: 0.4, y: 1.1, w: 10.9, colW: [3.4, 6.0, 1.5], rowH: 0.6, fontSize: 13 });
  T(s, "* for recommending existing MOFs and for properties in the table; no structure generation, no gas uptake without uptake labels", { x: 0.4, y: 7.25, w: 10.9, h: 0.4, fontSize: 11.5, italic: true, color: H.grey });

  // ===================================================== 29. Application
  pres.addSection({ title: "Application" });
  s = slide("Application: Streamlit Dashboard", "Application",
    "Live demo order is in docs/VIVA_GUIDE.md. Five pages: Chat, Explore & optimise, Predict & explain, Evaluation, About. The app also works with no language model.");
  await img(s, path.join(HERE, "shot_answer.png"), 0.35, 1.05, 5.4);
  await img(s, path.join(HERE, "shot_pareto.png"), 5.95, 1.05, 5.4);
  T(s, "“Which zinc MOFs have high surface area and low density?” — verified table", { x: 0.35, y: 3.75, w: 5.4, h: 0.3, fontSize: 11, italic: true, color: H.grey });
  T(s, "The same answer's NSGA-II Pareto plot (copper = recommended)", { x: 5.95, y: 3.75, w: 5.4, h: 0.3, fontSize: 11, italic: true, color: H.grey });
  const pages = [["Chat", "answer, verified table, Pareto plot, SHAP, sources, plan / SQL / validator trace, model used"], ["Explore & optimise", "filters + two-objective NSGA-II with Pareto plot"],
    ["Predict & explain", "prediction, 90 % interval, SHAP bars, FT attention"], ["Evaluation", "benchmark, model comparison, parity and SHAP plots"], ["About", "method summary and data sources"]];
  table(s, ["Page", "What it shows"], pages.map((p) => [{ text: p[0], options: { bold: true } }, p[1]]), { x: 0.35, y: 4.3, w: 11.0, colW: [2.3, 8.7], rowH: 0.42, fontSize: 12 });
  T(s, "Sidebar: choose any of the 14 language models (or none), planner mode (hybrid / LLM / rules), show plan and validation; system status of every component.",
    { x: 0.35, y: 7.0, w: 11.0, h: 0.6, fontSize: 12.5, color: H.navy });

  // ===================================================== 30. Conclusion
  pres.addSection({ title: "Conclusion" });
  s = slide("Conclusion and Future Work", "Conclusion", "Close with the key numbers and the honest limitations.");
  sub(s, "Conclusion", 0.4, 1.05, 5.4, H.navy);
  bullets(s, ["Exact answers over all 12,020 MOFs: held-out 5 % (review 1) → 100 % (default), 80 % fully offline",
    "Validated LLM planning with 14 free / local models and automatic fallback", "NSGA-II multi-objective ranking with application presets",
    `Surrogates: surface-area R² ${f3(sa.models.XGBoost.test_all.R2)}, 90 % interval covers ${pct(sa.conformal.test_coverage)}`,
    `Open-metal-site classification: XGBoost ROC-AUC ${f3(om.XGBoost.roc_auc)}, FT-Transformer ${f3(om["FT-Transformer"].roc_auc)}, MLP ${f3(om.MLP.roc_auc)} (baseline 0.5)`,
    "Answer validator keeps the LLM honest; every number in this deck comes from evaluate.py / evaluate_dl.py"], { x: 0.4, y: 1.45, w: 5.5, h: 5.8, fontSize: 13.5 });
  sub(s, "Limitations → future work", 6.2, 1.05, 5.2, H.red);
  table(s, ["Limitation", "Next step"], [["No gas-uptake labels", "Attach GCMC uptake data; reuse the surrogate pipeline"], ["No structure generation", "Diffusion / GA generator (e.g. MOFDiff)"],
    ["Offline model at 80 %", "LoRA fine-tuning of Llama 3 on plan examples"], ["Free-text reasoning unchecked", "Semantic-entropy style checks on sentences"],
    ["Heuristic presets", "Learned rules once uptake data exists"], ["Descriptor-only embeddings", "Structure / multimodal encoders (L²M³OF)"]],
  { x: 6.2, y: 1.45, w: 5.2, colW: [2.0, 3.2], rowH: 0.75, fontSize: 12 });

  // ===================================================== 31. References
  s = slide("References", "Conclusion", "IEEE-style list. All entries verified; the full annotated review is in docs/LITERATURE_REVIEW.md.");
  const refs = [
    "Y. Kang and J. Kim, “ChatMOF: an artificial intelligence system for predicting and generating metal-organic frameworks using large language models,” Nat. Commun., vol. 15, 4705, 2024.",
    "Y. G. Chung et al., “Advances, updates, and analytics for the computation-ready, experimental MOF database: CoRE MOF 2019,” J. Chem. Eng. Data, vol. 64, pp. 5985–5998, 2019.",
    "Y. Gorishniy, I. Rubachev, V. Khrulkov and A. Babenko, “Revisiting deep learning models for tabular data,” NeurIPS, 2021.",
    "L. Grinsztajn, E. Oyallon and G. Varoquaux, “Why do tree-based models still outperform deep learning on typical tabular data?” NeurIPS D&B, 2022.",
    "K. Deb, A. Pratap, S. Agarwal and T. Meyarivan, “A fast and elitist multiobjective genetic algorithm: NSGA-II,” IEEE Trans. Evol. Comput., vol. 6, pp. 182–197, 2002.",
    "S. M. Lundberg and S.-I. Lee, “A unified approach to interpreting model predictions,” NeurIPS, 2017.",
    "A. M. Bran et al., “Augmenting large language models with chemistry tools,” Nat. Mach. Intell., vol. 6, 2024.",
    "X. Fu, T. Xie, A. S. Rosen, T. Jaakkola and J. Smith, “MOFDiff: coarse-grained diffusion for metal-organic framework design,” ICLR, 2024.",
    "S.-A. Chen et al., “TableRAG: million-token table understanding with language models,” NeurIPS, 2024.",
    "Z. Wang et al., “Chain-of-Table: evolving tables in the reasoning chain for table understanding,” ICLR, 2024.",
    "S. Farquhar, J. Kossen, L. Kuhn and Y. Gal, “Detecting hallucinations in large language models using semantic entropy,” Nature, vol. 630, pp. 625–630, 2024.",
    "W. Lee, Y. Kang, T. Bae and J. Kim, “Harnessing large language models to collect and analyze MOF property data set,” J. Am. Chem. Soc., vol. 147, pp. 3943–3958, 2025.",
    "T. M. Pruyn et al., “MOF-ChemUnity: literature-informed large language models for metal–organic framework research,” J. Am. Chem. Soc., 2025.",
    "N. Hollmann et al., “Accurate predictions on small data with a tabular foundation model,” Nature, vol. 637, pp. 319–326, 2025.",
    "Y. Gorishniy, A. Kotelnikov and A. Babenko, “TabM: advancing tabular deep learning with parameter-efficient ensembling,” ICLR, 2025.",
    "Y. Chiang, E. Hsieh, C.-H. Chou and J. Riebesell, “LLaMP: large language model made powerful for high-fidelity materials knowledge retrieval,” EMNLP, 2025.",
    "T. J. Inizan et al., “System of agentic AI for the discovery of metal-organic frameworks,” arXiv:2504.14110, 2025.",
    "J. Cui et al., “L²M³OF: a large language multimodal model for metal-organic frameworks,” arXiv:2510.20976, 2025.",
    "J. Lin et al., “Conversational large-language-model AI agent for accelerated synthesis of MOF catalysts in olefin hydrogenation,” ACS Nano, vol. 19, pp. 23840–23858, 2025.",
    "C. Duan et al., “The rise of generative AI for metal-organic framework design and synthesis,” arXiv:2508.13197, 2025.",
    "H. Kim, D. Kim and J. Kim, “LitMOF: an LLM multi-agent for literature-validated MOF database correction and expansion,” arXiv:2512.01693, 2025.",
    "M. Pan et al., “Enhancing spatial reasoning in large language models for MOF structure prediction,” arXiv:2601.09285, 2026.",
    "Y. Chen et al., “An LLM agent for end-to-end computational materials discovery,” arXiv:2608.20434, 2026."];
  const half = 12;
  [refs.slice(0, half), refs.slice(half)].forEach((col, c) =>
    T(s, col.map((r, i) => R(`[${c * half + i + 1}] ${r}`, { breakLine: i < col.length - 1, paraSpaceAfter: 4 })), { x: 0.3 + c * 5.65, y: 1.05, w: 5.5, h: 6.8, fontSize: 10.5 }));

  // ===================================================== 32. Thank you
  s = pres.addSlide({ masterName: "TEMPLATE_BLANK", sectionTitle: "Conclusion" });
  T(s, "Thank You", { x: 0.5, y: 2.8, w: 10.69, h: 1.5, fontSize: 80, bold: true, color: "00B0F0", align: "center", valign: "middle" });
  T(s, "Questions and live demo  ·  github.com/Sai-Mohith24/MOFChat-AI-Driven-Material-Recommendation-", { x: 0.5, y: 4.6, w: 10.69, h: 0.5, fontSize: 14, color: H.grey, align: "center" });
  s.addNotes("Take questions or run the live demo (docs/VIVA_GUIDE.md, demo-day checklist).");

  // ===================================================== Appendix (backup slides)
  pres.addSection({ title: "Backup" });
  s = slide("Backup: Physics Rule as a Classifier", "Backup",
    "Backup slide. The descriptors were computed with a 3.31 Å probe; PLD below it means no accessible area. The rule is exact on the test set.");
  await img(s, fig("physics_rule.png"), 0.4, 1.0, 10.9, 5.6);
  T(s, `Rule: surface area = 0 if PLD < ${DL.physics.threshold_A.toFixed(4)} Å → test accuracy ${pct(DL.physics.accuracy, 2)} on ${DL.physics.n_test} MOFs.`, { x: 0.4, y: 7.0, w: 10.9, h: 0.4, fontSize: 13, bold: true, color: H.navy });

  s = slide("Backup: Demo Screenshots (if the live demo fails)", "Backup", "Backup slide with full-size screenshots of the running app.");
  await img(s, path.join(HERE, "app_home.png"), 0.3, 1.0, 5.5);
  await img(s, path.join(HERE, "app_pareto.png"), 5.95, 1.0, 5.5);
  T(s, "Chat page: 14 models, planner mode, system status", { x: 0.3, y: 4.5, w: 5.5, h: 0.3, fontSize: 11, italic: true, color: H.grey });
  T(s, "Pareto plot for the zinc question", { x: 5.95, y: 4.5, w: 5.5, h: 0.3, fontSize: 11, italic: true, color: H.grey });
  await img(s, path.join(HERE, "app_answer.png"), 3.1, 4.9, 5.5, 3.0);

  s = slide("Backup: How to Shorten the Talk", "Backup", "Not for presenting.");
  bullets(s, ["Full talk: slides 1–32 (about 25–30 minutes). 15-minute version: hide slides 2, 7, 8, 14, 17, 20, 25, 26 and 28; keep them for questions",
    "The 15-minute version still covers: introduction, base paper, objectives, literature, research gap, dataset, feature extraction, pipeline, models used, FT-Transformer architecture, NSGA-II, all main results (benchmark, classification metrics, confusion matrices, learning curves, regression, explainability), application, conclusion, references",
    "To hide a slide in PowerPoint: right-click the thumbnail → Hide Slide"], { x: 0.4, y: 1.2, w: 10.9, h: 3, fontSize: 15 });

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
}
build().catch((e) => { console.error(e); process.exit(1); });

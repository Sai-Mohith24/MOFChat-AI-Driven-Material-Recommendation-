# MOFChat: complete project summary (for learning with Claude chat)

> **Note to Claude (the chat assistant reading this):** I am Enku Sai Mohith (roll no. 24316), a member of Team 09 in the course 22AIE452 *Data Driven Material Modeling and Simulation*. This document describes our finished course project, MOFChat. Please use it to teach me the project from the basics up, explain any concept I ask about, and quiz me like a viva examiner. Stick to the facts in this document; if I ask about something it does not cover, say so instead of guessing.

---

## 1. The project in one paragraph

MOFChat is a chat assistant that helps a materials scientist choose **metal-organic frameworks (MOFs)**. You ask in plain English, for example "Find 3 MOFs with surface area above 4000 m²/g and void fraction above 0.8" or "best MOFs for CO2 capture", and it answers from a database of **12,020 real MOFs** (the CoRE MOF 2019 table, the same data used by our base paper, ChatMOF). A language model (LLM) turns the question into a **structured JSON plan**, never code. A **validator** checks the plan. The database is queried with **safe SQL**. Several goals at once are ranked with **NSGA-II** (Pareto fronts). Properties are predicted with **XGBoost** plus a calibrated interval and **SHAP** explanations, similar MOFs are found with **FT-Transformer embeddings**, and concept questions are answered with **RAG** over curated notes and the ChatMOF paper. Finally the LLM writes the answer, and an **answer validator** checks that every MOF ID, number and comparison in the text matches the database before it is shown. The LLM can be any of 14 free cloud models (Gemini, Groq, OpenRouter) or a local model (Llama 3 via Ollama), with automatic fallback.

Team 09: Amrutha T (24255), Charan Tej Reddy Y (24259), Poojitha D (24263), Enku Sai Mohith (24316), Ramu Jahna Bindu (24249).

---

## 2. Background

### 2.1 What a MOF is
MOFs are crystalline porous materials built from **metal nodes** connected by **organic linkers**. Their pores can be tuned, so they are candidates for carbon capture, hydrogen and methane storage, gas separation and catalysis. Choosing one means filtering thousands of structures on several properties at once, plus domain knowledge (which pore sizes let which gas molecules through, why open metal sites matter).

### 2.2 The geometric descriptors in our data
All were computed with the software **Zeo++** using a **3.31 Å probe** (the size of an N2 molecule).

| Column | Meaning | Unit |
|---|---|---|
| LCD | Largest cavity diameter: biggest sphere that fits anywhere inside the pores | Å |
| PLD | Pore limiting diameter: biggest sphere that can pass through the narrowest window | Å |
| LFPD | Largest free pore diameter: biggest sphere that can travel along the free path | Å |
| Density | Crystal density | g/cm³ |
| Surface_Area (ASA) | Probe-accessible surface area per gram (gravimetric) | m²/g |
| ASA_vol | Accessible surface area per volume (volumetric) | m²/cm³ |
| NASA_grav / NASA_vol | Non-accessible surface area (pockets the probe cannot reach) | m²/g, m²/cm³ |
| Void_Fraction | Fraction of the crystal volume that is accessible void (0–1) | – |
| Pore_Volume | Accessible pore volume per gram | cm³/g |
| NAV | Non-accessible volume | cm³/g |
| Metal_Type | Metal element(s) | – |
| Has_OMS / OMS_Type | Whether it has an open (coordinatively unsaturated) metal site, and which metal | – |

**Kinetic diameters** used for sieving (Å): H2O 2.65, H2 2.89, CO2 3.30, Ar 3.40, O2 3.46, Kr 3.60, N2 3.64, CO 3.76, CH4 3.80, Xe 4.10. If PLD is smaller than a gas's kinetic diameter, the MOF is treated as closed to that gas (a screening rule, not a hard law, because frameworks flex).

### 2.3 The base paper: ChatMOF
Kang & Kim, *Nature Communications* 15, 4705 (2024). A GPT-4 agent searches, predicts and generates MOFs from natural language by writing code and calling tools. Its own error analysis lists weaknesses that MOFChat targets:
1. Logic errors in LLM-written code.
2. Token-limit failures on large tables (4 % of search tasks).
3. Dependence on a proprietary, online LLM (GPT-4).
4. A dedicated pretrained model needed for every property.
5. No validation of the generated answer.
(It also searches only about 100 parent structures because of tokens, generates within 9 topologies, and has high compute cost.)

ChatMOF reports 96.9 % accuracy on its own 100 search questions (excluding token-limit failures). Our question set is different, so the numbers are not directly comparable.

---

## 3. The journey: review 1 → final version

### 3.1 What we built for review 1 (and why it failed)
- **Design:** a "two-tower" search. Each MOF was embedded with an FT-Transformer autoencoder (384-d), the question with Sentence-BERT (384-d), and the two were matched by cosine similarity in FAISS.
- **The flaw:** the two towers were **never trained together**. Equal dimensions do not make two vector spaces comparable; a real two-tower model needs contrastive training on (question, matching MOF) pairs. So the search effectively ignored the question.
- **Evidence:** "surface area > 4000 and void fraction > 0.8" returned 100 MOFs with a maximum surface area of 807 m²/g, although 206 MOFs actually satisfy it. "Recipe for chocolate cake" returned the identical 100 MOFs. On our benchmark the review-1 system scores **9.4 %** exact answers (development set) and **5 %** (held-out set).
- **Lesson:** numeric constraints are facts, so they belong in a database query (SQL), not in similarity search. The LLM should do what it is good at: understanding language.

### 3.2 Literature review correction
The review-1 literature table had serious problems: **6 of 15 papers could not be found anywhere** (treated as fabricated and removed), and several real ones had wrong authors (e.g. ChatMOF is by Y. Kang and J. Kim, not A. S. Rosen). The final review has **15 verified papers** (`docs/LITERATURE_REVIEW.md`). Key ones: ChatMOF; MOFTransformer (Kang et al., *Nat. Mach. Intell.* 2023); CoRE MOF 2019 (Chung et al., *J. Chem. Eng. Data* 2019); FT-Transformer (Gorishniy et al., NeurIPS 2021); "Why do tree-based models still outperform deep learning on tabular data?" (Grinsztajn et al., NeurIPS 2022); RAG (Lewis et al., NeurIPS 2020); TableRAG (Chen et al., NeurIPS 2024); Chain-of-Table (Wang et al., ICLR 2024); TARGET (Ji et al., 2024); TEM (Khanna & Subedi, 2024); ChatGPT Chemistry Assistant (Zheng et al., JACS 2023); MOF-ChemUnity (Pruyn et al., JACS 2025); L²M³OF (Cui et al., arXiv 2025); NSGA-II (Deb et al., IEEE TEC 2002); SHAP (Lundberg & Lee, NeurIPS 2017). Supporting tools: Sentence-BERT, FAISS, Zeo++.

### 3.3 The rebuild
The project was rebuilt around validated LLM planning + exact SQL, keeping the FT-Transformer only where it is valid (MOF-to-MOF similarity and property prediction). Then free cloud LLMs were added, six models were compared, the app was tested by hand, and four bugs found in testing were fixed.

---

## 4. Data and preprocessing (`setup_db.py`)

- **Source:** CoRE MOF 2019 descriptor table distributed with ChatMOF: **12,020 MOFs × 17 columns**.
- **ETL:** load the spreadsheet, normalise headers, rename to a clean schema, and **assert** each data-quality fact (so they are tested, not just observed):

| Check | Finding | Action |
|---|---|---|
| Missing values / duplicate rows / duplicate names | none | none |
| "Accessible volume volume fraction" vs "void fraction" | identical | dropped duplicate |
| "Accessible volume (cm³/g)" vs "Accessible pore volume" | identical | dropped duplicate |
| Pore volume vs void fraction / density | equal (max relative error 6×10⁻⁶) | documented as derived |
| Volumetric vs gravimetric surface area | ASA_vol = ASA × density | documented as derived |
| Zero surface area: 3,252 MOFs (27 %) | all have PLD < 3.31 Å (the probe cannot enter) — real, not missing data | exact "physics rule" in the models |
| Density unit | header says cm³/g, values are g/cm³ | label corrected |
| Multi-metal MOFs: 2,087 | comma-separated metals (65 metals overall) | separate normalised `mof_metals` table |

- **Output:** SQLite database `data/coremof.db` with tables `materials` (15 columns), `mof_metals` and `columns_doc`, indexed for common filters.
- The table holds **geometry only, no gas-uptake data**, so "CO2 capture" style answers are geometric screening heuristics, and the app says so.

---

## 5. Architecture

```
question
  │
  ▼
PLANNER: LLM writes a JSON plan  +  rule parser adds facts it is certain about ("hybrid")
  │
  ▼
PLAN VALIDATOR: columns, units, ranges, grounding ── errors go back to the LLM (≤ 2 retries) ── then rule-parser fallback
  │
  ▼
EXECUTOR (one of four tools)
  ├─ search / count : parameterised read-only SQL → NSGA-II ranking or closest-match fallback
  ├─ similar        : FT-Transformer embeddings + FAISS
  ├─ predict        : XGBoost + conformal interval + SHAP (FT-Transformer second opinion)
  └─ knowledge      : RAG (Sentence-BERT + FAISS) over curated notes + ChatMOF paper
  │
  ▼
ANSWER WRITER: LLM explains at most 10 verified rows
  │
  ▼
ANSWER VALIDATOR: MOF IDs, numbers and comparison claims must match the data → rewrite once → else flag
  │
  ▼
STREAMLIT APP: answer + verified table / prediction card + "why it fits" + Pareto plot + SHAP + sources + plan/SQL trace
```

---

## 6. Components in detail

### 6.1 Planner (`mofchat/llm.py`, `mofchat/rules.py`, `mofchat/agent.py`)
- The LLM gets a schema description, rules and **nine few-shot examples**, and runs at **temperature 0 in JSON mode**. It outputs a plan with: intent (search, count, lookup, similar, predict, knowledge, out_of_scope), numeric constraints, objectives (max/min), metals, open-metal-site flag, application, gases, MOF IDs, aggregate, prediction target and inputs, limit.
- Example for "Zinc MOFs with high surface area and low density":
  `{"intent":"search","metals":["Zn"],"objectives":[{"column":"Surface_Area","direction":"max"},{"column":"Density","direction":"min"}],"limit":5}`
- **Rule parser:** deterministic regular expressions (comparators, ranges, percentages, superlatives, metals, gases, applications) that produce the same plan structure. It is the fallback and a reproducible baseline.
- **Hybrid planner (default):** the LLM plan plus facts the rule parser is certain about: explicit numbers, metals, explicit limits and applications named by keyword.

### 6.2 Language models (`mofchat/llm.py`)
A registry of **14 models**; each reports whether it is usable right now (key present, package installed, server running).

| Provider | Models | Free-tier limit |
|---|---|---|
| Ollama (local, offline) | Llama 3 8B, Llama 3.1 8B, Qwen 2.5 7B, Nemotron Mini 4B | none (your laptop) |
| Google Gemini | 3.5 Flash, 3.8 Flash, 3.1 Flash-Lite, Flash-Lite latest | about 10–15 requests/min |
| Groq | GPT-OSS 120B, GPT-OSS 20B, Qwen 3.8 27B | 8,000 tokens/min, 1,000 requests/day per model |
| OpenRouter | Nemotron 3 Super 120B, Nemotron 3 Ultra 550B, Gemma 4 31B (`:free`) | about 50 requests/day |

- Every call goes through one function that **throttles** each model to its free-tier budget (a sliding 60-second window of requests and tokens). On a rate limit or outage (HTTP 429/503) it **falls back** to the next model; if every model fails, the rule parser plans and a template writes the answer, so a question is always answered.
- **Default order** (chosen from the evaluation): Gemini 3.1 Flash-Lite → GPT-OSS 120B → Qwen 3.8 27B → local Llama 3.
- API keys live in a git-ignored `.env` file. The app's sidebar picks the model, and every answer says which model wrote it.

### 6.3 Plan validator (`mofchat/validator.py`)
- Resolves column aliases from one registry (`config.py`), e.g. "porosity" → void fraction.
- Normalises operators, directions and percentages (80 % → 0.8).
- Rejects unknown columns, non-numeric values, and physically impossible values the LLM invented (a value the user typed is kept, with a note).
- **Grounding:** a threshold that does not appear in the question becomes a preference (objective) instead of a filter; MOF IDs not mentioned in the question are dropped.
- Merges duplicate bounds and flags contradictions (e.g. density > 2 and < 1).
- Repairs a common slip: "lowest X" written as a constraint without a value → an objective.
- For application questions, drops ranking objectives the question does not mention, so the application preset decides the ranking.
- Expands application presets into explicit, explained constraints and objectives.
- Errors go back to the LLM for up to 2 corrections, then the rule plan is used.

### 6.4 Executor (`mofchat/tools.py`, `mofchat/optimizer.py`)
- The plan is compiled into SQL with **whitelisted column names and bound parameters**, on a **read-only** connection, so injection or a wrong column is impossible. The LLM never writes SQL that runs.
- One objective → plain sort. Two or more → **NSGA-II selection**:
  1. **Non-dominated sorting** splits candidates into Pareto fronts. Front 1 = MOFs that no other MOF beats in every objective.
  2. **Crowding distance** inside a front prefers MOFs in sparse regions, so the list shows diverse trade-offs.
  - We use NSGA-II's selection operator (not the full genetic algorithm) because we rank MOFs that already exist. Two objectives use an exact O(n log n) sweep: all 12,020 MOFs in 0.02 s (three objectives: 2.6 s). MOFs in the worst 25 % of any objective are screened out first (NSGA-II otherwise keeps extreme points).
- **No exact match** (e.g. surface area > 20,000) → the closest MOFs, ranked by total constraint violation in robust standard deviations, and the user is told clearly.

### 6.5 Application presets (`mofchat/config.py`, `knowledge/applications.md`)

| Application | Constraints / objectives |
|---|---|
| H2 storage | PLD ≥ 2.89 Å; maximise gravimetric surface area and void fraction (Chahine's rule) |
| CH4 storage | PLD ≥ 3.80 Å; maximise volumetric surface area and void fraction |
| CO2 capture | open metal site; PLD ≥ 3.30 Å; maximise volumetric surface area, minimise LCD |
| Size-sieving separation of A/B | d_A ≤ PLD ≤ d_B (kinetic diameters); maximise void fraction |
| Catalysis | open metal site; PLD ≥ 5 Å; maximise surface area and PLD |

These are explicitly heuristics, because the dataset has no adsorption data.

### 6.6 FT-Transformer and similarity search (`mofchat/ft_transformer.py`, `train_ft.py`)
- **Architecture** (Gorishniy et al. 2021): each numeric descriptor x_j becomes a token x_j·W_j + b_j; categorical features (primary metal, open metal site) become embeddings; a [CLS] token is prepended; three pre-norm Transformer blocks (d = 64, 4 heads).
- **Self-supervised embedding model:** 30 % of descriptor tokens are replaced by a learned [MASK] token and the [CLS] state must reconstruct all ten descriptors (masked autoencoder). 114,378 parameters, 85/15 split, early stopping (38 epochs, 63 s). L2-normalised [CLS] vectors are indexed with FAISS (inner product = cosine).
- "MOFs similar to HKUST-1" (CSD refcode FIQCEN) returns its nearest neighbours.

### 6.7 Property prediction (`train_property_models.py`, `mofchat/properties.py`)
- **Targets:** surface area (from density, LCD, PLD, LFPD, void fraction, pore volume) and void fraction (from density, LCD, PLD, LFPD; pore volume excluded because it would leak the target).
- **Split:** 70/10/10/10 = train / validation (early stopping) / calibration (conformal) / test.
- **Models compared:** mean baseline, Ridge, Gaussian process (RBF kernel with one length scale per feature + noise, on a 2,000-sample subset because exact GPR is O(n³)), **XGBoost (production)**, FT-Transformer regressor.
- **Physics rule:** PLD below the 3.31 Å probe → surface area exactly 0; regressors train on accessible MOFs only.
- **Split-conformal 90 % interval:** half-width = 90th percentile of absolute errors on the calibration split.
- **SHAP (TreeExplainer)** explains each prediction feature by feature; the FT-Transformer gives a second opinion and attention maps.

### 6.8 Knowledge retrieval / RAG (`setup_vectorstore.py`, `mofchat/knowledge.py`)
- Corpus: five curated notes with references (dataset definitions, kinetic diameters and sieving, application heuristics, MOF basics, MOFChat methods) + the ChatMOF paper (13 pages) = **104 chunks**.
- Embeddings: Sentence-BERT all-MiniLM-L6-v2, normalised, FAISS inner product. If the best match is below **0.30 cosine**, the question is treated as off-topic and politely declined.

### 6.9 Answer writer and answer validator
The LLM writes a short answer from at most 10 verified rows, a percentile-based "why it fits" for each MOF, notes and cited snippets. The validator then:
1. extracts every ID-like token and every number (including "8 318" written with a narrow space);
2. corrects IDs within edit distance 2 of a real result (e.g. ACOCLUS → ACOCUS);
3. flags unknown IDs and numbers not traceable to the table, the question or a known constant (within rounding);
4. checks **comparison claims** about named MOFs: in "A, B and C have surface areas ≥ 6000 m²/g", each MOF must really meet it; "first Pareto front" claims are checked against the NSGA-II ranks;
5. asks the LLM to rewrite once with the exact problems listed;
6. flags anything still wrong. The verified table (or a prediction card) is always shown.
It does **not** check free-text reasoning without numbers (e.g. a wrong formula in a sentence).

### 6.10 The Streamlit app (`app.py`, `app_pages/`)
Five pages: **Chat** (answer, verified table or prediction card, "why it fits", Pareto plot, SHAP, sources, plan/SQL/validator trace, which model answered); **Explore & optimise** (filters + two-objective NSGA-II with Pareto plot); **Predict & explain** (prediction, interval, SHAP, FT attention); **Evaluation** (all metrics and figures); **About**. It works with no LLM at all (rule planner + template answers).

---

## 7. Evaluation and results (`evaluate.py`, `docs/RESULTS.md`)

### 7.1 How we evaluated
- **Development set:** 64 labelled questions in 10 categories: single constraint, multiple constraints, metal/open metal site, superlative, multi-objective, application, count/average, lookup/similar, impossible request, knowledge/off-topic.
- **Held-out set:** 20 new phrasings written **after** the rule parser was tuned, never used for tuning → the honest estimate of generalisation. (One question = 5 points.)
- **Gold answers:** each question has a hand-written gold plan, run through the same executor (which is unit-tested against pandas).
- **Metrics:** exact answer match (exactly the gold MOFs / count / average, or correctly declined), constraint precision@k (share of returned MOFs that satisfy all gold filters), plan accuracy, latency.
- **Systems compared:** review-1 two-tower, rules only, LLM single shot (no validator), LLM + validator, hybrid (default).

### 7.2 Main results (default model Gemini 3.1 Flash-Lite)

| System | Development (64) exact | Held-out (20) exact |
|---|---:|---:|
| Review-1 two-tower | 9.4 % | 5 % |
| Rules only (no LLM) | 100 % | 80 % |
| Flash-Lite single shot / + validator / hybrid | 100 / 100 / 100 % | 100 / 100 / 100 % |
| Local Llama 3 8B single shot → + validator → hybrid | 85.9 → 93.8 → 100 % | 65 → 70 → 80 % |

**Key insight:** for a strong model the safety layers change nothing and cost under 0.01 s; for the small offline model they add 15 points on held-out questions. The validator is what makes MOFChat usable offline.

### 7.3 Model comparison (each model alone, fallback switched off)

| Model | Held-out exact | Median time per planning call | Provider errors |
|---|---:|---:|---:|
| Gemini 3.1 Flash-Lite (default) | 20/20 | 1.5 s (10.6 s while Google's free tier was overloaded) | 13 of 84 |
| GPT-OSS 120B (Groq) | 19/20 | 2.4–4.7 s | 0 |
| Qwen 3.8 27B (Groq) | 19/20 | 20 s (reasoning model; Groq token limit) | 0 |
| Nemotron 3 Super 120B (OpenRouter; held-out only) | 19/20 | 2.0 s | 0 |
| Llama 3 8B (local, hybrid) | 16/20 | 1.5 s | 0 |
| Gemini 3.5 Flash | no score | – | daily free quota ran out (429 RESOURCE_EXHAUSTED) |

- The three 19/20 models all miss the same question, "Is there any MOF with density above 8 g/cm³?", answering with a count of 0, arguably also correct. So the cloud models are effectively tied on accuracy; they differ in reliability and speed.
- Llama 3's held-out errors: "natural gas" storage mapped to hydrogen storage; an H2/CH4 sieving question mapped to hydrogen storage; an extra objective added; the density-above-8 question answered with a count.

### 7.4 Answer validation (16 full answers per model)

| Model | First drafts with a problem | Rewritten | Still flagged | LLM call failed |
|---|---:|---:|---:|---:|
| Gemini 3.1 Flash-Lite | 0 | 0 | 0 | 0 |
| Llama 3 8B | 2 (3 invented numbers; garbled ID OFEUN06 → OFERUN06) | 1 | 0 | 0 |
| GPT-OSS 120B | 2 (rewrite added a false "Pareto front 1" claim → flagged) | 2 | 1 | 0 |
| Qwen 3.8 27B | 0 | 0 | 0 | 7 (Groq limits; template shown) |

### 7.5 Property prediction (held-out 10 % test split)

| Target | Model | MAE | RMSE | R² |
|---|---|---:|---:|---:|
| Surface area (m²/g) | Mean baseline | 609.7 | 915.5 | 0.343 |
| | Ridge | 157.8 | 261.0 | 0.947 |
| | Gaussian process | 97.8 | 170.9 | 0.977 |
| | **XGBoost** | **90.0** | **152.3** | **0.982** |
| | FT-Transformer | 92.5 | 153.7 | 0.982 |
| Void fraction | Mean baseline | 0.096 | 0.119 | 0.000 |
| | Ridge | 0.044 | 0.056 | 0.780 |
| | Gaussian process | 0.041 | 0.054 | 0.796 |
| | **XGBoost** | **0.037** | **0.049** | **0.828** |
| | FT-Transformer | 0.039 | 0.050 | 0.823 |

- 90 % conformal interval: ±288 m²/g for surface area, covering **90.5 %** of test MOFs (void fraction ±0.078, 88.4 %). GPR 95 % intervals cover 93.9 % and 95.1 %.
- Physics rule: 100 % accurate on test (it doesn't raise accuracy because XGBoost learns it, but zero predictions become exact and explainable).
- SHAP: pore volume (628) and void fraction (235) dominate surface area; density dominates void fraction. Physically sensible: more accessible void means more accessible wall.
- XGBoost and FT-Transformer are statistically tied (matches Grinsztajn et al.); XGBoost trains ~400× faster (0.25 s vs 112 s) and gives exact TreeSHAP, so it is the production model.

### 7.6 Similarity (1,000 random query MOFs, 10 neighbours each)

| Neighbours from | Mean descriptor difference | Same metal | Same open-metal-site flag |
|---|---:|---:|---:|
| FT embedding | 0.077 σ | 27.8 % | 70.2 % |
| Raw descriptor k-NN (upper bound on this metric) | 0.068 σ | 22.8 % | 66.4 % |
| Random | 0.952 σ | 8.0 % | 55.7 % |

Overlap of FT and k-NN neighbour lists: 62 %.

### 7.7 Knowledge retrieval
hit@1 75 %, hit@3 83 % on 12 questions with a known source; 92 % of in-domain questions accepted; 5/5 off-topic questions rejected.

---

## 8. What testing the finished app found (all fixed, each with a unit test)
The benchmark scores plans, not the written text, so these only appeared when we used the app with GPT-OSS 20B:
1. **False comparison claim** ("the remaining three have ≥ 6000 m²/g" when UHUPOD01 has 4,564) passed the number check → validator now checks comparison and Pareto-front claims per MOF.
2. **"Best MOFs for CO2 capture"** was ranked by the LLM's own objectives, silently replacing the CO2 preset → objectives not in the question are dropped.
3. **A prediction question got no prediction:** the validator flagged "90 %" (the interval level), the rewrite request made the model refuse to quote the number → interval level is now a known constant, the prompt says how to report predictions, and the chat always shows a prediction card.
4. **"8 318" written with a narrow space** was read as "318" → narrow/no-break spaces are read as thousands separators.
The full evaluation was re-run after the fixes. 38 unit tests pass.

---

## 9. Limitations and future work
- No gas-uptake or selectivity labels, so application answers are heuristics. Next step: attach GCMC uptake data (hMOF/CoRE) and train the same surrogates on it.
- Recommendation only: no structure generation (ChatMOF has a genetic algorithm).
- The local 8B model still mis-plans some phrasings (80 % held-out); LoRA fine-tuning on plan examples would help.
- Free tiers have quotas and overloads; fallback hides them but cannot remove them.
- The answer validator does not check free-text reasoning without numbers.
- Similarity could use structure-based embeddings (e.g. MOFTransformer) for chemistry-aware neighbours.

## 10. How MOFChat answers ChatMOF's weaknesses
| ChatMOF weakness | MOFChat |
|---|---|
| LLM-written code with logic errors | JSON plan, validated field by field; SQL compiled from a whitelist |
| Token-limit failures | SQL filters all 12,020 MOFs first; the LLM sees at most 10 rows |
| Proprietary online GPT-4 | 14 free/local models, automatic fallback, works with no LLM |
| A pretrained model per property | Surrogates trained directly on the table, with calibrated intervals |
| No validation of answers | Answer validator for IDs, numbers and comparison claims |
| No multi-objective selection / explanations | NSGA-II, Pareto plots, SHAP, "why it fits" percentiles |

---

## 11. Files and how to run
Project folder: `Sem-5/Data-Driven/Final-project/` (git branch `complete-project`; GitHub repo Sai-Mohith24/MOFChat-AI-Driven-Material-Recommendation-).

| Path | What it is |
|---|---|
| `app.py`, `app_pages/` | Streamlit app (5 pages) |
| `mofchat/config.py` | single source of truth: columns, units, aliases, ranges, presets |
| `mofchat/rules.py`, `mofchat/llm.py` | rule parser; LLM registry, throttling, fallback, prompts |
| `mofchat/validator.py` | plan and answer validation |
| `mofchat/tools.py`, `mofchat/optimizer.py` | SQL executor, closest-match fallback, NSGA-II |
| `mofchat/ft_transformer.py`, `mofchat/similarity.py` | FT-Transformer, similarity search |
| `mofchat/properties.py` | prediction + SHAP at runtime |
| `mofchat/knowledge.py`, `knowledge/` | RAG retrieval and curated notes |
| `setup_db.py`, `setup_vectorstore.py`, `train_ft.py`, `train_property_models.py` | build steps |
| `evaluate.py`, `benchmark/` | benchmark (64 + 20 questions), model comparison |
| `tests/` | 38 unit tests |
| `docs/` | PROJECT_REPORT, RESULTS, VIVA_GUIDE, LITERATURE_REVIEW, LIMITATIONS_VS_SOLUTIONS |
| `reviews/` | review-1 deliverables; final-review slides |
| `*.ipynb` | a notebook copy of every `.py` file |

Run: `cd Final-project && source venv/bin/activate && streamlit run app.py`. Rebuild everything: `python run_pipeline.py`. Tests: `python -m pytest -q`. Evaluation: `python evaluate.py` (1.5–2 hours because of free-tier rate limits).

---

## 12. Glossary (ask Claude to explain any of these)
MOF · CoRE MOF · Zeo++ · probe diameter · LCD / PLD / LFPD · void fraction · gravimetric vs volumetric surface area · open metal site · kinetic diameter · molecular sieving · Chahine's rule · LLM · temperature 0 · JSON mode · few-shot prompting · rule-based parser · hybrid planner · grounding · parameterised SQL / SQL injection · NSGA-II · Pareto front / dominance · crowding distance · XGBoost · Ridge regression · Gaussian process regression (RBF, ARD) · split-conformal prediction · SHAP / TreeSHAP · FT-Transformer · [CLS] token · masked autoencoder / self-supervised learning · embeddings · cosine similarity · FAISS · two-tower model / contrastive training · Sentence-BERT · RAG · hit@k · exact match · precision@k · held-out set vs development set · rate limit (HTTP 429) · fallback chain · Levenshtein (edit) distance · Streamlit.

## 13. Likely viva questions (short answers)
- **Why not let the LLM write SQL?** A JSON plan is small and can be checked field by field; columns come from a whitelist and values are bound parameters on a read-only connection.
- **What changed after review 1?** We measured our two-tower search (9.4 % / 5 %), found the towers were never trained together, and replaced it with validated planning + exact SQL.
- **Why NSGA-II?** With two goals there is no single best MOF; Pareto fronts + crowding distance give diverse trade-offs.
- **Why XGBoost over the FT-Transformer?** Tied accuracy (R² 0.982), 400× faster training, exact TreeSHAP.
- **How do you know the intervals are right?** Split-conformal: 90.5 % test coverage for a 90 % interval.
- **Which LLM and why?** Flash-Lite was best on held-out (20/20); the others tie at 19/20, so reliability and speed decide; local Llama 3 for offline.
- **Why keep the validator if the cloud model gets 100 %?** Free for strong models, essential for the offline model (+15 points), insurance on bad provider days.
- **How do you stop hallucination?** The LLM only sees verified rows; the answer validator checks IDs, numbers and comparison claims, rewrites once, flags the rest; the true table is always shown.
- **Are your papers real?** Yes now: 15 verified; 6 fabricated review-1 entries removed.

## 14. Suggested ways to learn with Claude
- "Explain the whole pipeline step by step using the question 'Zinc MOFs with high surface area and low density'."
- "Teach me NSGA-II with a tiny example of 5 MOFs."
- "Explain split-conformal prediction and why our coverage is 90.5 %."
- "Why did our review-1 two-tower search fail? Explain like I'm new to embeddings."
- "Quiz me with 10 viva questions on this project, one at a time, and grade my answers."

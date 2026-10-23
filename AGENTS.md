# AGENTS.md: MOFChat handoff (read this first)

This file hands the MOFChat project from Claude Code to Codex (or any coding agent). It covers the goal, every component, the data, the results, how to run and rebuild things, the conventions the user cares about, and the traps that cost time before. Written 2026-10-23 from the code at commit `998d500` (branch `complete-project`, working tree clean).

**Re-verify before you rely on a detail.** Numbers come from `docs/RESULTS.md` (evaluation of 2026-10-08) and `docs/DL_RESULTS.md` (2026-10-22). If the code or a result file disagrees with this file, the code and result files win.

---

## 0. TL;DR

- **What it is:** MOFChat, a chat assistant that recommends metal-organic frameworks (MOFs) from the 12,020-row CoRE MOF 2019 table. An LLM turns the question into a **JSON plan, never code**. A validator checks the plan. The plan runs as **parameterised read-only SQL**. **NSGA-II** ranks results on several objectives. **XGBoost + conformal interval + SHAP** predict properties, **FT-Transformer embeddings + FAISS** find similar MOFs, and **RAG** answers concept questions. An **answer validator** checks every MOF ID, number and comparison claim in the LLM's text against the data. The UI is a Streamlit app.
- **Who:** Team 09, course **22AIE452 Data Driven Material Modeling and Simulation** (Amrita). The user is **Enku Sai Mohith (roll 24316)**. Teammates: Amrutha T (24255), Charan Tej Reddy Y (24259), Poojitha D (24263), Ramu Jahna Bindu (24249).
- **Base paper:** ChatMOF, Kang & Kim, *Nature Communications* 15, 4705 (2024). PDF at `knowledge/papers/ChatMOF.pdf`.
- **Status:** finished. Final review is on the **evening of 2026-10-23**. The deliverable is the PowerPoint `reviews/final_review/MOFChat_Final_Review.pptx` (36 slides). The user wants a **presentation .pptx, not a written paper**.
- **Canonical folder:** `/Users/saimohith/Documents/Sem-5/Data-Driven/Final-project/` (this folder). It has its own `venv/`, git repo and `.env`. GitHub: `Sai-Mohith24/MOFChat-AI-Driven-Material-Recommendation-`, branch `complete-project`.
- **Run:** `cd Final-project && source venv/bin/activate && streamlit run app.py --server.port 8502`
- **Test:** `python -m pytest -q` (38 tests).

---

## 1. Hard rules (the user's standing preferences)

1. **Every `.py` file needs a synced `.ipynb` twin next to it.** The `.py` file is the source of truth. After editing any `.py` file, run:
   ```bash
   python tools/py_to_ipynb.py . --sync
   ```
   `--sync` creates missing notebooks and refreshes generated ones. It never overwrites a hand-made notebook that has outputs (e.g. `reviews/1st_review/02_data_preprocessing.ipynb`, `../Class/svr_stock_regression.ipynb`). When a hand-made notebook doesn't contain the script's code, it writes `NAME_from_py.ipynb` beside it instead. Claude had a PostToolUse hook (`.claude/settings.json`) that did this automatically; **Codex has no such hook, so run `--sync` yourself.** `.git/hooks/pre-commit` also syncs staged `.py` files. `coremof/__init__.py` (an empty dataset file outside this folder) is skipped on purpose.
2. **Never print, log or commit API keys.** They live in the git-ignored `.env` (template: `.env.example`). Don't `cat .env`.
3. **Never tune anything on `benchmark/heldout.json`.** It is the honest generalisation test (20 questions written after the rule parser was tuned).
4. **Never invent references.** The review-1 literature table contained 6 fabricated papers. Only the verified list in `docs/LITERATURE_REVIEW.md` (15 papers) and the deck's 18 verified 2024–2026 papers may be cited.
5. **Write in plain, short, factual English** (docs, slides, commit messages). Report results honestly, including failures and quota problems.
6. Git: commit only when asked. End commit messages the way the history does (short imperative subject). Don't push without being asked.

---

## 2. Folder map

### 2.1 Workspace `/Users/saimohith/Documents/Sem-5/Data-Driven/`

| Path | What it is |
|---|---|
| `Final-project/` | **The canonical project. Work here.** |
| `Final-project.zip` | ~600 MB zip snapshot from 2026-10-21. Don't edit it. |
| `Project-antigravity/` | Older working copy of the same project (before the final polish). Don't edit it; kept for history. |
| `1st_Review_Data-driven/` (+ `.zip`) | Review-1 deliverables (scripts 02–08, decks). Copied into `Final-project/reviews/1st_review/`. |
| `mof_recommender/` | The very first prototype (10 rows of dummy data). Copied into `Final-project/history/`. |
| `coremof/`, `hMOF/`, `24287731/`, `tables/` | Raw data downloads (CIF/grid files, the descriptor spreadsheet). `tables/coremof.xlsx` is the source table. hMOF is unused. |
| `ChatMOF.pdf` | Base paper (copy also in `Final-project/knowledge/papers/`). |
| `Class/`, `Study Materials/` | Unrelated course lecture material and a class exercise (SVR stock regression). |
| `.claude/launch.json` | Dev-server configs: `final-project` on port **8502**, older `mofchat` (Project-antigravity) on 8501. |

### 2.2 This folder (`Final-project/`)

| Path | Purpose |
|---|---|
| `app.py`, `app_pages/` | Streamlit app. Pages: `chat.py`, `explore.py` (Explore & optimise), `predict.py` (Predict & explain), `evaluation.py`, `about.py`. |
| `mofchat/` | The package (section 4). |
| `setup_db.py` | ETL: `data/coremof.xlsx` → `data/coremof.db` (SQLite) with asserted data-quality facts. |
| `setup_vectorstore.py` | Builds the RAG index (`artifacts/knowledge_index/`) from `knowledge/*.md` + `knowledge/papers/ChatMOF.pdf`. |
| `train_ft.py` | Trains the self-supervised FT-Transformer masked autoencoder → `artifacts/ft_embeddings/` (model, embeddings, FAISS index). |
| `train_property_models.py` | Trains surface-area and void-fraction surrogates (mean, Ridge, GPR, XGBoost, FT-Transformer) → `artifacts/property_models/`. |
| `run_pipeline.py` | Runs the four build steps above, then pytest. `--eval` also runs `evaluate.py`. |
| `evaluate.py` | Benchmark (64 dev + 20 held-out), six-model comparison, answer validation, knowledge retrieval → `artifacts/eval/`, `docs/RESULTS.md`. |
| `evaluate_dl.py` | Classification metrics, learning curves and feature-extraction graphs → `artifacts/dl_eval/`, `docs/DL_RESULTS.md`. |
| `agent_core.py` | Compatibility shim: `MOFHybridAgent.answer_query()` for the review-1 scripts. |
| `benchmark/queries.json`, `benchmark/heldout.json` | Questions with gold plans (`{"id","category","question","gold":{plan}}`). |
| `knowledge/` | Curated RAG notes: `applications.md`, `coremof_dataset.md`, `mofchat_methods.md`, `mofs_basics.md`, `pore_geometry_and_gases.md`, plus `papers/ChatMOF.pdf`. |
| `data/` | `coremof.xlsx` (source), `coremof_cleaned.csv`, `coremof.db` (built). |
| `artifacts/` | All trained models, indexes, metrics JSON and figures (section 6). `artifacts/baseline_review1/` (the review-1 FAISS index) is git-ignored. |
| `tests/test_core.py`, `tests/test_llm.py` | 28 + 10 = 38 unit tests. |
| `tools/py_to_ipynb.py` | The notebook-twin generator (rule 1). |
| `docs/` | `PROJECT_REPORT.md` (full write-up), `RESULTS.md`, `DL_RESULTS.md`, `VIVA_GUIDE.md` (demo script + likely questions), `LITERATURE_REVIEW.md`, `LIMITATIONS_VS_SOLUTIONS.md`, `PROJECT_SUMMARY_FOR_CHAT.md` (a long plain-language summary; good for teaching). |
| `reviews/1st_review/` | Review-1 deliverables: `DDMS_R1.pptx` (corrected), `DDMS_R1_original.pptx` (untouched), scripts 02–08 + notebooks, review docs (marked superseded where the design changed). |
| `reviews/final_review/` | **Final deck** `MOFChat_Final_Review.pptx` + `.pdf`, generator `pptx_source/build.js`, an older 16-slide Claude Slides version (`deck_source/`, link in its README). |
| `reviews/archive/` | Original review-1 zip files, unchanged. |
| `history/mof_recommender_prototype/` | First prototype. |
| `.streamlit/config.toml`, `mofchat/theme.py` | UI theme (section 4.11). |
| `.env` / `.env.example` | API keys (git-ignored) / template. |
| `*.ipynb` | Notebook twin of every `.py`. |
| `.claude/`, `.agents/` | Claude/agent settings and a Streamlit skill. Git-ignored. |

---

## 3. Data (CoRE MOF 2019 descriptor table)

- **Source:** the table distributed with ChatMOF. **12,020 MOFs × 17 source columns.** All geometric descriptors were computed with **Zeo++** using a **3.31 Å probe** (N2), `config.PROBE_DIAMETER_A`.
- **SQLite schema** (`data/coremof.db`): table `materials` (15 columns), `mof_metals` (normalised one-row-per-metal, for multi-metal MOFs), `columns_doc`. Indexed for common filters. The app opens it **read-only**.
- **Columns** (registry in `mofchat/config.py` → `COLUMNS`, the single source of truth for names, labels, units, aliases and valid ranges):

| Column | Meaning | Unit |
|---|---|---|
| `MOF_ID` | CSD refcode or source-file name | – |
| `LCD` | Largest cavity diameter | Å |
| `PLD` | Pore limiting diameter (narrowest window) | Å |
| `LFPD` | Largest free pore diameter | Å |
| `Density` | Crystal density (spreadsheet header wrongly says cm³/g) | g/cm³ |
| `Surface_Area` | Accessible surface area, gravimetric | m²/g |
| `ASA_vol` | Accessible surface area, volumetric (= ASA × density) | m²/cm³ |
| `NASA_grav` / `NASA_vol` | Non-accessible surface area | m²/g, m²/cm³ |
| `Void_Fraction` | Accessible void fraction (0–1) | – |
| `Pore_Volume` | Accessible pore volume (= void fraction / density exactly) | cm³/g |
| `NAV` | Non-accessible volume | cm³/g |
| `Metal_Type` | Comma-separated metals (65 metals; 2,087 multi-metal MOFs) | – |
| `Has_OMS` / `OMS_Type` | Open metal site flag (66.4 % have one) / which metal | – |

- **Asserted data facts** (`setup_db.py` asserts them, so they're tested, not just observed):
  - No missing values, duplicate rows or duplicate names.
  - Two source columns are exact duplicates and are dropped ("Accessible volume volume fraction" = void fraction; "Accessible volume (cm³/g)" = accessible pore volume).
  - **Surface area is exactly 0 for all 3,252 MOFs (27 %) with PLD < 3.31 Å**: the probe can't enter. That's real, not missing data. The models use it as an exact "physics rule".
  - Pore volume = void fraction / density (max relative error 6×10⁻⁶).
- **No gas-uptake or adsorption labels exist locally.** Every "CO2 capture / H2 storage" answer is a **geometric screening heuristic**, and the app says so.
- **Kinetic diameters** (Å, `config.KINETIC_DIAMETERS_A`): H2O 2.65, H2 2.89, CO2 3.30, Ar 3.40, O2 3.46, Kr 3.60, N2 3.64, CO 3.76, CH4 3.80, Xe 4.10.
- **Well-known names** (`config.COMMON_NAMES`): HKUST-1 / Cu-BTC / MOF-199 → `FIQCEN`; MOF-5 / IRMOF-1 → `SAHYIK`; ZIF-8 → `OFERUN`; UiO-66 → `RUBTAK`.

---

## 4. Architecture and code walkthrough

```
question ─► PLANNER  (mofchat/agent.py MOFChatAgent.plan)
              LLM JSON plan (mofchat/llm.py)  +  rule parser (mofchat/rules.py)  = "hybrid"
              │
              ▼
           PLAN VALIDATOR (mofchat/validator.py validate_plan)
              errors fed back to the LLM ≤ 2 retries ─► else rule-plan fallback
              │
              ▼
           EXECUTOR (MOFChatAgent.execute → mofchat/tools.py)
              search/count/lookup : parameterised read-only SQL ─► NSGA-II (optimizer.py) / closest-match fallback
              similar             : FT-Transformer embeddings + FAISS (similarity.py)
              predict             : XGBoost + conformal interval + SHAP, FT second opinion (properties.py)
              knowledge           : Sentence-BERT + FAISS over notes + ChatMOF.pdf (knowledge.py)
              │
              ▼
           ANSWER WRITER (llm.write_answer, ≤ 10 verified rows) ─► ANSWER VALIDATOR (validator.validate_answer)
              │                                                     rewrite once with the listed problems, else flag
              ▼
           STREAMLIT (mofchat/ui.py render_response): answer + verified table / prediction card + "why it fits"
              + Pareto plot + SHAP + sources + plan/SQL/validator trace + which model answered
```

### 4.1 `mofchat/__init__.py` and `mofchat/_faiss.py` (import order: critical on macOS)
XGBoost, PyTorch and faiss each bundle their own libomp. `_faiss.py` sets `KMP_DUPLICATE_LIB_OK=TRUE` and `OMP_NUM_THREADS=1`, then imports **xgboost → torch → faiss** in that order, and sets faiss and torch to 1 thread (`MOFCHAT_THREADS` overrides torch's thread count). **Every entry point must `import mofchat` first.** Other orders segfault or deadlock. Multi-threaded torch segfaulted in `train_ft.py` (8 threads, 2026-10-21), so training stays single-threaded.

### 4.2 `mofchat/plan.py`: the plan contract
`QueryPlan` dataclass: `intent` ∈ {search, similar, lookup, count, predict, knowledge, out_of_scope}; `constraints: [Constraint(column, op ∈ {>,>=,<,<=,==}, value)]`; `objectives: [Objective(column, direction max|min)]`; `metals`; `open_metal_site: bool|None`; `application`; `gases`; `mof_ids`; `aggregate {"func": count|avg|min|max, "column"}`; `target_property`; `feature_values`; `limit` (default 5, max 50); `limit_explicit`; `notes` (shown to the user); `source` (rules | llm | llm+rules). Use `to_dict` / `from_dict` / `summary`.

### 4.3 `mofchat/config.py`
Paths (`DB_PATH`, `ARTIFACTS_DIR`, etc.; overridable with `MOFCHAT_DB`, `MOFCHAT_DATASET`), `COLUMNS` registry with aliases (e.g. "porosity" → `Void_Fraction`), `resolve_column`, `unit_of`, kinetic diameters, gas aliases, `APPLICATIONS` presets, `COMMON_NAMES`, `RANDOM_SEED = 42`, `TEXT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"`.

**Application presets** (heuristics, explained to the user):

| Key | Constraints / objectives |
|---|---|
| `h2_storage` | PLD ≥ 2.89; max Surface_Area, max Void_Fraction (Chahine's rule) |
| `ch4_storage` | PLD ≥ 3.80; max ASA_vol, max Void_Fraction |
| `co2_capture` | open metal site; PLD ≥ 3.30; max ASA_vol, min LCD |
| `gas_separation` | d_small ≤ PLD ≤ d_large (kinetic diameters of the two gases); max Void_Fraction |
| `catalysis` | open metal site; PLD ≥ 5; max Surface_Area, max PLD |

### 4.4 `mofchat/rules.py`: deterministic rule parser
`parse(query) -> QueryPlan`. Regexes for comparators ("above", "at least", "between", "+", "or more"), numbers with `k` and `%`, units, approximations ("around 0.6"), superlatives (`MAX_WORDS`/`MIN_WORDS`), limits ("top 3", number words), MOF IDs and common names, metals (element names and symbols; ambiguous symbols like In/As/Co/Al need context, see `AMBIGUOUS_SYMBOLS`), negation ("without OMS"), gases, application keywords, and intent (similar/predict/count/average/concept question/out of scope). It's the fallback planner, the no-LLM mode, and a reproducible baseline (100 % dev, 80 % held-out).

### 4.5 `mofchat/llm.py`: model registry, throttling, fallback, prompts
- **14 models** (`MODELS`, `ModelSpec`):
  - Ollama (local): `llama3-local`, `llama3.1-local`, `qwen2.5-local`, `nemotron-mini-local`
  - Google: `gemini-3.5-flash`, `gemini-3.8-flash`, `gemini-3.1-flash-lite`, `gemini-flash-lite-latest` (thinking switched off or low for speed)
  - Groq: `gpt-oss-120b`, `gpt-oss-20b`, `qwen3.8-27b` (8,000 tokens/min binding limit)
  - OpenRouter `:free`: `nemotron-super-free`, `nemotron-ultra-free`, `gemma4-31b-free` (~50 requests/day in total)
- **There is no "Gemini 2.1 Flash"; `gemini-2.5-flash` returns 404.** Groq retired its Llama 3.x endpoints in 2026.
- `DEFAULT_ORDER = ["gemini-3.1-flash-lite", "gpt-oss-120b", "qwen3.8-27b", "llama3-local"]`, chosen from the model comparison. `MOFCHAT_MODEL` / `MOFCHAT_FALLBACK` in `.env` override it.
- `chat(messages, model_id, json_mode)` walks the fallback chain. `_throttle` keeps a sliding 60 s window per model (requests and estimated tokens). On 429/503 it moves to the next model. If JSON mode is refused, it retries the same model without JSON mode. `MAX_WAIT_S = 10` in the app (rather fall back than wait); the evaluation raises it. `FALLBACK_ENABLED = False` in the evaluation so each answer is attributed to one model.
- Prompts: `PLANNER_SYSTEM` + nine few-shot `EXAMPLES` (temperature 0, JSON mode) and `ANSWER_SYSTEM`. `llm_plan()` and `write_answer()` are the entry points.
- CLI: `python -m mofchat.llm --list` (which models are usable) and `--probe` (one real request to each configured model; uses free quota).

### 4.6 `mofchat/validator.py`: plan and answer validation (the core safety layer)
**`validate_plan(raw, query, expand, predictable) -> (QueryPlan, errors)`:**
- Normalises intent, operator, direction and application synonyms; resolves column aliases; converts percentages (80 % → 0.8).
- Rejects unknown columns, non-numeric values, and physically impossible values the LLM invented. A value the user typed is kept, with a note.
- **Grounding:** a threshold that doesn't appear in the question becomes an objective instead of a filter (`query_numbers`, `_grounded`). MOF IDs not in the question are dropped.
- `_merge_bounds` merges duplicate bounds and flags contradictions.
- Repairs "lowest X" written as a constraint without a value into an objective.
- For application questions, drops objectives the question doesn't mention (`_column_mentioned`, with everyday words like "light" → Density, "porous" → Void_Fraction), so the preset decides the ranking.
- `expand_application` turns a preset into explicit, explained constraints and objectives.

**`validate_answer(text, results, allowed, ...)`:**
- Extracts ID-like tokens (`_id_candidates`, with `STOP_TOKENS` and an English-word filter) and numbers (`_numbers`). Commas and narrow/no-break spaces count as thousands separators ("8 318").
- IDs within Levenshtein distance 2 of a real result are corrected (e.g. ACOCLUS → ACOCUS). Other unknown IDs are flagged.
- Numbers must match the table, the question, or a known constant (`allowed_numbers`, rounding-aware `_matches`). The interval level "90 %" is a known constant.
- `_false_claims` checks comparison claims per named MOF ("A, B and C have ≥ 6000 m²/g", collective "these/remaining", negation/exception handling) and "first/second Pareto front" claims against NSGA-II ranks.
- The agent asks the LLM to rewrite once with the exact problems listed, then flags anything left. It does **not** check numberless free-text reasoning.

### 4.7 `mofchat/agent.py`: orchestration (`MOFChatAgent`)
- `__init__(use_llm=True, planner_mode="hybrid"|"llm"|"rules", max_retries=2, validate_answers=True, model_id=None)`.
- `plan()`: the rule plan is always computed. In LLM mode it loops up to 3 attempts, feeding validator errors back. If no attempt passes, it uses the rule plan with a note. In hybrid mode, `_merge` adds facts the rule parser is certain of: explicit constraints, metals, OMS flag, explicit application keyword (wins over the LLM's guess), gases, explicit limit, MOF IDs. If the LLM says knowledge/out_of_scope but the rules found explicit filters, the rule plan is used.
- `execute()` dispatches by intent. `predict` uses MOF rows (with the actual value shown) or user-given `feature_values`.
- `answer()`: knowledge/out_of_scope goes to RAG, and a question below the relevance threshold is declined politely. Otherwise it executes, adds a percentile-based `why_text` per row, attaches SHAP for the top 5 rows, attaches RAG snippets, writes a template answer, then the LLM answer plus validation. Returns `AgentResponse` (answer, plan, table, result, predictions, shap, snippets, trace, validation, timings, models_used).

### 4.8 `mofchat/tools.py` and `mofchat/optimizer.py`: execution
- `compile_where(plan)`: SQL from **whitelisted column names + bound parameters** (`SQL_OPS`). The LLM never writes SQL that runs. `render_sql` exists for display only.
- `search`: with 0–1 objectives, a plain SQL sort. With 2+ objectives, `nsga2_rank`.
- `closest_matches`: when nothing matches (e.g. surface area > 20,000), it ranks by total constraint violation in robust standard deviations and says so clearly.
- `aggregate` (count/avg/min/max), `lookup`, `similar`, `display_frame`.
- **NSGA-II selection operator only** (not the genetic algorithm; we rank existing MOFs): `non_dominated_fronts` (an exact O(n log n) 2-D sweep `_front_2d`, chunked dominance for 3+ objectives) + `crowding_distance`. MOFs in the worst 25 % of any objective are screened out first. Timing: 12,020 MOFs in 0.02 s for 2 objectives, 2.6 s for 3. `pareto_front_mask` serves the plots.

### 4.9 ML components
- **`features.py`**: `Preprocessor` (log transform of skewed columns, standardisation, categorical encoding of the primary metal (metals with fewer than 30 MOFs grouped as "other") and `Has_OMS`). `PROPERTY_TARGETS`: Surface_Area from density, LCD, PLD, LFPD, void fraction, pore volume. Void_Fraction from density, LCD, PLD, LFPD (pore volume excluded: it would leak the target).
- **`ft_transformer.py`** (Gorishniy et al. 2021): `FeatureTokenizer` (x_j·W_j + b_j per numeric feature; embeddings for categoricals), [CLS] token, 3 pre-norm Transformer blocks, d = 64, 4 heads. `FTRegressor` and `FTMaskedAutoencoder`: 30 % of tokens replaced by a learned [MASK] token, and the [CLS] state reconstructs all ten descriptors. 114,378 parameters, 85/15 split, early stopping at 38 epochs, 63 s.
- **`similarity.py`**: L2-normalised [CLS] embeddings in a FAISS inner-product index (`artifacts/ft_embeddings/index.faiss`).
- **`properties.py`**: `predict(target, inputs, actual)` → `Prediction` with the XGBoost value, **split-conformal 90 % interval** (half-width = 90th percentile of absolute calibration errors), the physics rule (PLD < 3.31 → surface area exactly 0), SHAP (TreeExplainer), an FT-Transformer second opinion and attention. Missing inputs are filled with medians. `explain_rows` computes SHAP for result tables.
- **Training split** (`train_property_models.py`): 70/10/10/10 = train / validation (early stopping) / calibration (conformal) / test. GPR uses an RBF kernel with ARD + noise on a 2,000-sample subset (exact GPR is O(n³)).
- **`knowledge.py`**: Sentence-BERT `all-MiniLM-L6-v2` + FAISS. 104 chunks (5 notes + 13-page ChatMOF PDF). `RELEVANCE_THRESHOLD = 0.30` cosine: below it, the question counts as off-topic.

### 4.10 `mofchat/db.py`
`connect` (read-only URI), `query_df`, cached `load_materials`, `id_index` (case-insensitive ID lookup), `resolve_metal` (names and symbols, e.g. "aluminum" → Al), `resolve_mof_id` (refcodes + common names), `get_rows`.

### 4.11 UI: `app.py`, `app_pages/`, `mofchat/ui.py`, `mofchat/theme.py`
- `app.py`: `import mofchat` first, page config, theme, a DB-missing guard, and a sidebar with the model picker (from `llm.list_models()`), planner mode and details toggle. `st.navigation` loads the five pages.
- `ui.py`: `@st.cache_resource get_agent(...)`, Altair `pareto_chart` and `shap_chart`, `render_prediction`, `render_response`.
- **Theme "crystal lattice"** (2026-10-21): HKUST-1 teal `#0E7490` + copper accents, navy sidebar `#0B1F2A`, Space Grotesk / IBM Plex fonts. Settings in `.streamlit/config.toml`; masthead, lattice motif, cards and status list in `theme.py`. **`st.html` strips inline `<svg>`, so drawings go in as `<img>` data URIs.**
- **Streamlit caches the agent and does not hot-reload `mofchat/` modules (theme CSS included). Restart the server after editing them.**
- Port **8502** (8501 is usually the user's separate bone-fracture DL app).
- The app works with no LLM at all (rule planner + template answers).

---

## 5. Evaluation (`evaluate.py`, `evaluate_dl.py`)

### 5.1 Method
- **Dev set:** 64 questions in 10 categories (single constraint, multiple constraints, metal/OMS, superlative, multi-objective, application, count/average, lookup/similar, impossible request, knowledge/off-topic). **Held-out set:** 20 questions (one question = 5 points).
- Gold plans are run through the same (unit-tested) executor. Metrics: exact answer match, constraint precision@k, plan accuracy, latency.
- Systems: review-1 two-tower, rules only, LLM single shot, LLM + validator, hybrid.
- CLI: `python evaluate.py` runs everything: ~1.5–2 h because Groq's 8,000 tokens/min makes about 1 call in 4 wait ~60 s, so report the **median** latency. Flags: `--no-llm` (fast), `--only answers|knowledge|models` (re-run one part and rewrite `docs/RESULTS.md` without redoing the benchmark), `--models`, `--model`, `--answers`. Run it in the background. It consumes free-tier quota.
- `python evaluate_dl.py` writes `artifacts/dl_eval/metrics.json`, figures, and `docs/DL_RESULTS.md`.

### 5.2 Headline results (default model Gemini 3.1 Flash-Lite)

| System | Dev exact (64) | Held-out exact (20) |
|---|---:|---:|
| Review-1 two-tower | 9.4 % | 5 % |
| Rules only | 100 % | 80 % |
| Flash-Lite single shot / + validator / hybrid | 100 / 100 / 100 % | 100 / 100 / 100 % |
| Local Llama 3 8B single shot → + validator → hybrid | 85.9 → 93.8 → 100 % | 65 → 70 → 80 % |

Takeaway: for a strong model the safety layers are free (< 0.01 s). For the offline 8B model they add 15 points on held-out questions.

**Model comparison** (held-out, fallback off): Flash-Lite 20/20 (median 1.5 s; 13 of 84 provider errors on an overloaded day). GPT-OSS 120B, Qwen 3.8 27B (20 s, reasoning model) and Nemotron 3 Super 120B each 19/20. All three miss "Is there any MOF with density above 8 g/cm³?" by answering with a count of 0, which is arguably also correct. Llama 3 8B hybrid 16/20. Gemini 3.5 Flash: no score (daily quota exhausted, 429).

**Answer validation** (16 answers per model): Flash-Lite 0 problems. Llama 3: 2 drafts with problems (invented numbers; garbled OFEUN06 → OFERUN06), fixed. GPT-OSS 120B: 2 rewritten, 1 still flagged (a false "Pareto front 1" claim). Qwen: 7 LLM calls failed on Groq limits, so the template answer was shown.

**Property prediction** (10 % test split):

| Target | Model | MAE | RMSE | R² |
|---|---|---:|---:|---:|
| Surface area | Mean / Ridge / GPR | 609.7 / 157.8 / 97.8 | 915.5 / 261.0 / 170.9 | 0.343 / 0.947 / 0.977 |
| | **XGBoost** / FT-Transformer | **90.0** / 92.5 | **152.3** / 153.7 | **0.982** / 0.982 |
| Void fraction | Mean / Ridge / GPR | 0.096 / 0.044 / 0.041 | 0.119 / 0.056 / 0.054 | 0.000 / 0.780 / 0.796 |
| | **XGBoost** / FT-Transformer | **0.037** / 0.039 | **0.049** / 0.050 | **0.828** / 0.823 |

- Conformal 90 % interval: ±288 m²/g with 90.5 % test coverage (void fraction ±0.078, 88.4 %).
- The physics rule is 100 % accurate.
- SHAP: pore volume and void fraction dominate surface area; density dominates void fraction.
- XGBoost ≈ FT-Transformer (consistent with Grinsztajn et al. 2022). XGBoost trains ~400× faster (0.25 s vs 112 s) and gives exact TreeSHAP, so it is the production model.

**Similarity** (1,000 queries × 10 neighbours): FT embedding 0.077 σ mean descriptor difference, 27.8 % same metal. Raw k-NN 0.068 σ, 22.8 %. Random 0.952 σ, 8.0 %. 62 % overlap with the k-NN lists.

**Knowledge retrieval:** hit@1 75 %, hit@3 83 %. 5/5 off-topic questions rejected. Off-topic ROC-AUC 0.981.

**DL classification (`docs/DL_RESULTS.md`):** open-metal-site classifier (test accuracy / ROC-AUC): **XGBoost 0.750 / 0.787** (best), MLP 0.734 / 0.756, FT-Transformer 0.728 / 0.755, logistic regression 0.693 / 0.676, majority 0.663. Planner intent accuracy: rules 0.964, Flash-Lite hybrid 0.988, Llama 3 hybrid 0.988. PCA: 2 components explain 78 % of the variance; LCD–LFPD correlation +0.99.

### 5.3 Bugs found by hand-testing the app (all fixed, each with a unit test)
1. A false comparison claim ("remaining three ≥ 6000 m²/g" when UHUPOD01 has 4,564) passed the number check → per-MOF claim checking added.
2. "Best MOFs for CO2 capture" was ranked by the LLM's own objectives → objectives not mentioned in the question are dropped.
3. A prediction question got no prediction (the "90 %" interval level was flagged as an unknown number) → it's now a known constant, and a prediction card is always shown.
4. "8 318" with a narrow space was read as 318 → narrow/no-break spaces count as thousands separators.

---

## 6. Artifacts (all built by the pipeline; don't hand-edit)

| Path | Contents |
|---|---|
| `artifacts/ft_embeddings/` | `model.pt`, `preprocessor.json`, `embeddings.npy`, `ids.json`, `index.faiss`, `metrics.json`, `training_curve.png` |
| `artifacts/property_models/<Target>/` | `xgb.json`, `ft.pt`, `ft_preprocessor.json`, `meta.json` (conformal width, features, medians); plus `metrics.json`, parity and SHAP PNGs |
| `artifacts/knowledge_index/` | FAISS store for RAG |
| `artifacts/eval/` | `summary.json`, `benchmark_results.csv`, `model_comparison.csv`, PNGs |
| `artifacts/dl_eval/` | `metrics.json` + 15 figures (ROC/PR, confusion matrices, learning curves, PCA, t-SNE, correlations, physics rule) |
| `artifacts/baseline_review1/` | Review-1 FAISS index, used only to score the old system (git-ignored) |

Rebuild everything: `python run_pipeline.py` (~10 min). The final-review deck reads these JSON files at build time.

---

## 7. Final-review deck

- **File:** `reviews/final_review/MOFChat_Final_Review.pptx` (36 slides: 34 + 2 appendix), plus `MOFChat_Final_Review.pdf`. Style follows the review-1 template: A4 landscape (11.69 × 8.27 in), Amrita logo, blue heading bars, Arial. **One body text size, 12 pt; titles 24 pt. No speaker notes** (the user asked for none).
- **Contents:** problem; ChatMOF weaknesses; 18 verified 2024–2026 papers + research gap; data and feature-extraction graphs; dashboard-to-backend and offline/online pipelines; how each model works (two slides); FT-Transformer architecture; planner/validator; NSGA-II; surrogates; benchmark; OMS classification (accuracy, ROC-AUC, confusion matrices, train/val/test curves); regression + learning curves; intent and off-topic classification; explainability; app screenshots; limitations; conclusion; references.
- **Generator:** `reviews/final_review/pptx_source/build.js` (pptxgenjs + sharp). It reads `artifacts/dl_eval/metrics.json`, `artifacts/property_models/metrics.json`, `artifacts/eval/summary.json`, `artifacts/ft_embeddings/metrics.json` and `pptx_source/pareto.json`, and requires `applyTheme` from `$PPTX_SKILL/scripts/apply_theme.js`. **That file came from Claude's pptx skill and is not in this repo.** To rebuild without it, replace that `require` with a no-op or reimplement the theme step. Prefer editing the existing .pptx minimally if only text changes are needed.
  ```bash
  cd reviews/final_review/pptx_source && npm install pptxgenjs sharp && PPTX_SKILL=<dir> node build.js
  ```
- **Visual QA:** LibreOffice is **not installed**. Export to PDF through the installed Microsoft PowerPoint with `osascript`, then look at the pages.
- `reviews/final_review/deck_source/` + the README link is an older 16-slide Claude Slides version (claude.ai artifact). It's superseded by the .pptx. The README section at the top of this repo still mentions "16-slide deck"; that's stale.
- Demo script and likely viva questions: `docs/VIVA_GUIDE.md`. Good demo questions:
  - "Find 3 MOFs with surface area > 4000 m²/g and void fraction > 0.8" (206 exist)
  - "Zinc MOFs with high surface area and low density" (NSGA-II + Pareto plot)
  - "Best MOFs for CO2 capture"
  - "MOFs similar to HKUST-1"
  - "Predict the surface area of a MOF with density 0.6, void fraction 0.75, LCD 11 Å, PLD 7 Å"
  - "MOFs with surface area > 20,000" (closest matches)
  - "recipe for chocolate cake" (declined)

---

## 8. Project history (why the design is what it is)

1. **Prototype** (`history/mof_recommender_prototype/`): 10 rows of dummy data, LangChain + Llama 3.
2. **Review 1** (snapshot commit `ab9caa5`): a "two-tower" retrieval. MOFs were embedded by an FT-Transformer autoencoder (384-d) and questions by Sentence-BERT (384-d), matched by cosine in FAISS. **Flaw:** the towers were never trained together (no contrastive training), so the search ignored the question. "Surface area > 4000 and void fraction > 0.8" returned MOFs with a maximum of 807 m²/g, and "chocolate cake" returned the same 100 MOFs. Measured: 9.4 % dev / 5 % held-out. The literature table had 6 fabricated papers and wrong authors (ChatMOF is by Kang & Kim, not Rosen).
3. **Rebuild** (`cdf41e6`): numeric constraints are facts, so they go to SQL. The LLM only does language → JSON plan, with validators. The FT-Transformer is kept only where valid (MOF-to-MOF similarity, property prediction).
4. **Finish** (`1a0e3ce`): free cloud LLMs, six-model comparison, stricter answer validation, docs.
5. Notebook twins (`7527a99`); chat summary doc (`d65ffa5`); "crystal lattice" theme + single-threaded FT training (`4d0c1ac`); final-review deck + DL evaluation (`8b41ece`, `b89cca5`, `998d500`).

**How MOFChat answers ChatMOF's weaknesses:**

| ChatMOF weakness | MOFChat's answer |
|---|---|
| LLM-written code with logic errors | Validated JSON plan; SQL compiled from a whitelist |
| Token-limit failures | SQL filters first; the LLM sees ≤ 10 rows |
| Proprietary GPT-4 | 14 free/local models with fallback; works with no LLM |
| A pretrained model per property | Surrogates on the table with calibrated intervals |
| No answer validation | Answer validator for IDs, numbers and claims |
| No multi-objective ranking or explanations | NSGA-II, SHAP, "why it fits" percentiles |

**Limitations / future work:**
- No adsorption labels: attach GCMC uptake data (hMOF/CoRE) and train the same surrogates.
- No structure generation.
- Llama 3 8B reaches 80 % held-out: LoRA fine-tuning on plan examples would help.
- Free-tier quotas.
- No checking of numberless reasoning.
- Structure-aware embeddings (MOFTransformer) would give chemistry-aware neighbours.

---

## 9. Gotchas checklist

- `import mofchat` before anything that touches xgboost, torch or faiss. Keep torch single-threaded.
- Restart Streamlit after editing `mofchat/` (no hot reload; the agent is cached).
- Ollama may not be running: start it with `ollama serve` (or the Ollama app). Without it, local models show as unavailable; nothing crashes.
- `python -m mofchat.llm --probe` and `evaluate.py` spend free-tier quota. Gemini 3.5 Flash's daily quota ran out before.
- Full evaluation takes 1.5–2 h. Run it in the background and use `--only` for partial re-runs.
- Don't change `benchmark/heldout.json` or tune against it.
- After any `.py` edit: `python tools/py_to_ipynb.py . --sync`.
- `.env` holds real keys: never print or commit it. `.claude/`, `.agents/`, `.idea/`, `venv/`, `artifacts/baseline_review1/` are git-ignored.
- Python 3.14 venv on macOS Apple silicon; pinned versions are in `requirements.txt`.
- Density's source header says cm³/g, but the values are g/cm³.
- If you change any result, re-check the deck's numbers. Every slide number comes from `docs/RESULTS.md` / `artifacts/*.json`.

---

## 10. Where to learn more

`docs/PROJECT_SUMMARY_FOR_CHAT.md` (complete plain-language walkthrough with glossary and viva Q&A) → `docs/PROJECT_REPORT.md` (full report) → `docs/RESULTS.md` / `docs/DL_RESULTS.md` (all numbers) → `docs/VIVA_GUIDE.md` (demo + questions) → the code in section 4 order: `plan.py`, `config.py`, `rules.py`, `llm.py`, `validator.py`, `agent.py`, `tools.py`, `optimizer.py`, the ML modules, `ui.py`.

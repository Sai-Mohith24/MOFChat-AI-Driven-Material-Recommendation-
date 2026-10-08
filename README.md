# MOFChat: explainable, data-grounded MOF recommendation

MOFChat is a conversational assistant for choosing **metal-organic frameworks (MOFs)**. It answers plain-English questions over the **12,020-MOF CoRE-MOF 2019 table** (the dataset behind ChatMOF, Kang & Kim, *Nat. Commun.* 2024).

- It works with **free cloud LLMs** (Google Gemini, Groq, OpenRouter) or **fully offline** with local Ollama models, and falls back automatically when a free tier is rate-limited.
- The language model never invents data. Every MOF and every number comes from the database, and every answer is checked before it is shown.

Course project for 22AIE452 Data Driven Material Modeling and Simulation, Team 09.

## What is in this folder (`Final-project/`)

| Path | Contents |
|---|---|
| this folder (root) | the complete, runnable MOFChat project: code, database, trained models, results, docs, notebooks, git history (branch `complete-project`) |
| `venv/` | ready-to-use Python environment (`source venv/bin/activate`) |
| `docs/` | **start here**: `PROJECT_REPORT.md`, `RESULTS.md`, `VIVA_GUIDE.md`, `LITERATURE_REVIEW.md`, `LIMITATIONS_VS_SOLUTIONS.md` |
| `*.ipynb` | notebook version of every `.py` file |
| `knowledge/papers/` | the base paper `ChatMOF.pdf` (used by the knowledge index) |
| `reviews/1st_review/` | review-1 deliverables: corrected deck `DDMS_R1.pptx`, untouched `DDMS_R1_original.pptx`, scripts 02–08 and notebooks, review docs (marked as superseded where the design changed) |
| `reviews/final_review/` | final-review slides (link to the 16-slide deck with speaker notes, plus the slide sources) |
| `reviews/archive/` | the original review-1 zip files, unchanged |
| `history/mof_recommender_prototype/` | the very first prototype (10 rows of dummy data) |

Quick start: `cd Final-project && source venv/bin/activate && streamlit run app.py`.

## What it can do

| Ask… | MOFChat… |
|---|---|
| "Find 3 MOFs with surface area > 4000 m²/g and void fraction > 0.8" | turns the question into a validated plan, runs parameterised read-only SQL, and returns the exact matches (206 exist; top 3 shown) |
| "Zinc MOFs with high surface area and low density" | ranks the candidates on several objectives with **NSGA-II** (Pareto fronts + crowding distance) and plots the Pareto front |
| "Best MOFs for CO2 capture" / "separate CO2 from N2" | applies transparent screening heuristics (open metal sites, pore-size windows from kinetic diameters) and explains them |
| "MOFs similar to HKUST-1" | searches **self-supervised FT-Transformer embeddings** with FAISS |
| "Predict the surface area of a MOF with density 0.6, void fraction 0.75, LCD 11 Å, PLD 7 Å" | predicts with **XGBoost** (90 % conformal interval), explains with **SHAP**, and adds an FT-Transformer second opinion |
| "How many Cu MOFs have open metal sites?" / "average density of Zr MOFs" | counts and averages exactly in SQL |
| "MOFs with surface area > 20,000" | says clearly that none exist and shows the closest ones |
| "What is the pore limiting diameter?" | answers from a cited knowledge base (curated notes + the ChatMOF paper) |
| "recipe for chocolate cake" | politely declines (off-topic detection) |

## Architecture

```
question ─► planner (LLM JSON plan: Gemini / Groq / OpenRouter / local Ollama, with fallback  +  rule parser)
              │
              ▼
           validator ── errors fed back to the LLM (≤ 2 retries) ─► rule-parser fallback
              │  (whitelisted columns, units, physical ranges, grounded numbers & IDs, contradictions,
              │   application presets)
              ▼
           executor ─ search/count: parameterised read-only SQLite ─► NSGA-II ranking / closest-match fallback
                    ─ similar:      FT-Transformer embeddings + FAISS
                    ─ predict:      XGBoost + conformal interval + SHAP, FT-Transformer second opinion
                    ─ knowledge:    Sentence-BERT + FAISS over curated notes and ChatMOF.pdf
              │
              ▼
           LLM answer writer ─► answer validator (MOF IDs, numbers and comparison claims must match
                                     the results; garbled IDs corrected, otherwise regenerate / flag)
              │
              ▼
           Streamlit app: answer + verified table + "why it fits" + Pareto plot + SHAP + sources + plan/SQL trace
```

Results (benchmark, property models, embeddings) are in [docs/RESULTS.md](docs/RESULTS.md); the full write-up is in [docs/PROJECT_REPORT.md](docs/PROJECT_REPORT.md).

## Language models

The planner and answer writer can use any of these (`python -m mofchat.llm --list` shows which are ready):

| Provider | Models | Key in `.env` | Free-tier limit |
|---|---|---|---|
| Ollama (local) | Llama 3 8B, Llama 3.1 8B, Qwen 2.5 7B, Nemotron Mini | none | none (your CPU) |
| Google Gemini | Gemini 3.5 Flash, 3.8 Flash, 3.1 Flash-Lite, Flash-Lite latest | `GOOGLE_API_KEY` | about 10–15 requests/min |
| Groq | GPT-OSS 120B, GPT-OSS 20B, Qwen 3.8 27B | `GROQ_API_KEY` | 8,000 tokens/min and 1,000 requests/day per model |
| OpenRouter | Nemotron 3 Super 120B, Nemotron 3 Ultra 550B, Gemma 4 31B (`:free`) | `OPENROUTER_API_KEY` | about 50 requests/day |

- Copy `.env.example` to `.env` and add the keys you have. Every key is optional; models without a key show as unavailable.
- Pick the model in the app's sidebar, or set `MOFCHAT_MODEL` in `.env`.
- When a free tier is rate-limited or down (429/503), MOFChat moves to the next model (`MOFCHAT_FALLBACK`, then the default order), then to the rule-based planner, so a question is always answered.
- `python -m mofchat.llm --probe` sends one real request to every configured model.
- There is no "Gemini 2.1 Flash". The live model list (October 2026) offers 3.x Flash models; `gemini-2.5-flash` returns 404.
- **Default model:** Gemini 3.1 Flash-Lite, then GPT-OSS 120B, Qwen 3.8 27B and local Llama 3. In the comparison of six models ([docs/RESULTS.md](docs/RESULTS.md), section 1b), Flash-Lite answered all 20 held-out questions exactly and the other cloud models 19; local Llama 3 reaches 80 % with the validator and hybrid planner.

## Setup

Prerequisites: Python 3.10+ (tested on 3.14). Optional: API keys in `.env` for the free cloud models, and/or [Ollama](https://ollama.com) with `ollama pull llama3` for offline use. With neither, MOFChat uses its rule-based planner and template answers.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py          # builds DB, knowledge index, embeddings, property models; runs tests
streamlit run app.py
```

`run_pipeline.py --eval` additionally runs the full evaluation: about 1.5–2 hours, mostly waiting for free-tier rate limits. `python evaluate.py --only answers|knowledge|models` re-runs one part.

## Repository layout

| Path | Purpose |
|---|---|
| `app.py`, `app_pages/` | Streamlit app: Chat, Explore & optimise, Predict & explain, Evaluation, About |
| `mofchat/config.py` | single source of truth: columns, units, aliases, physical ranges, application presets |
| `mofchat/rules.py`, `mofchat/llm.py` | rule-based parser; multi-provider model registry (Gemini, Groq, OpenRouter, Ollama) with rate limiting and fallback, planner and answer-writer prompts |
| `mofchat/validator.py` | plan validation/repair and answer validation |
| `mofchat/tools.py`, `mofchat/optimizer.py` | SQL executor, closest-match fallback, NSGA-II |
| `mofchat/ft_transformer.py`, `mofchat/similarity.py` | FT-Transformer (regressor + masked autoencoder), similarity search |
| `mofchat/properties.py` | property prediction + SHAP at runtime |
| `mofchat/knowledge.py`, `knowledge/` | RAG retrieval and the curated knowledge notes |
| `setup_db.py`, `setup_vectorstore.py`, `train_ft.py`, `train_property_models.py` | build steps |
| `evaluate.py`, `benchmark/` | 64-question development benchmark + 20-question held-out set |
| `tests/` | 38 unit tests (`python -m pytest -q`) |
| `docs/` | report, results, literature review, viva guide |
| `agent_core.py` | compatibility shim for the review-1 scripts |
| `*.ipynb` | a notebook twin of every `.py` file (same code, split into cells). The `.py` files are the source of truth; regenerate the notebooks after edits with `python tools/py_to_ipynb.py . --overwrite` |

## Notes

- **Data facts:**
  - The surface area of all 3,252 MOFs with pore limiting diameter < 3.31 Å is exactly 0, because that is the probe size used to compute the descriptors.
  - Pore volume = void fraction / density exactly.
  - Two spreadsheet columns are duplicates.
  - The density column is mislabelled cm³/g (the values are g/cm³).
- **What the recommendations are:** the table contains geometry only. "CO2 capture" or "H2 storage" recommendations are geometric screening heuristics, not adsorption predictions.
- **macOS:** XGBoost, PyTorch and faiss each bundle OpenMP. `mofchat/_faiss.py` fixes the import order and threading, so always `import mofchat` first.

## License

Academic use. Respect the licences of the CoRE-MOF data and Meta's Llama 3.

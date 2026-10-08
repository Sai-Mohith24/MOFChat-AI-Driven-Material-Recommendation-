# MOFChat: explainable, data-grounded MOF recommendation

MOFChat is a conversational assistant for choosing **metal-organic frameworks (MOFs)**. It answers plain-English questions over the **12,020-MOF CoRE-MOF 2019 table** (the dataset behind ChatMOF, Kang & Kim, *Nat. Commun.* 2024).

- It runs **fully offline** with a local Llama 3 model.
- The language model never invents data. Every MOF and every number comes from the database, and every answer is checked before it is shown.

Course project for 22AIE452 Data Driven Material Modeling and Simulation, Team 09.

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
question ─► planner (Llama 3 JSON plan  +  deterministic rule parser)
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
           Llama 3 answer writer ─► answer validator (MOF IDs and numbers must match the results;
                                     garbled IDs corrected, otherwise regenerate / flag)
              │
              ▼
           Streamlit app: answer + verified table + "why it fits" + Pareto plot + SHAP + sources + plan/SQL trace
```

Results (benchmark, property models, embeddings) are in [docs/RESULTS.md](docs/RESULTS.md); the full write-up is in [docs/PROJECT_REPORT.md](docs/PROJECT_REPORT.md).

## Setup

Prerequisites: Python 3.10+ (tested on 3.14), and optionally [Ollama](https://ollama.com) with `ollama pull llama3`. Without Ollama, MOFChat uses its rule-based planner and template answers.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py          # builds DB, knowledge index, embeddings, property models; runs tests
streamlit run app.py
```

`run_pipeline.py --eval` additionally runs the full evaluation (about 15 minutes with Ollama).

## Repository layout

| Path | Purpose |
|---|---|
| `app.py`, `app_pages/` | Streamlit app: Chat, Explore & optimise, Predict & explain, Evaluation, About |
| `mofchat/config.py` | single source of truth: columns, units, aliases, physical ranges, application presets |
| `mofchat/rules.py`, `mofchat/llm.py` | rule-based parser; Llama 3 planner and answer writer |
| `mofchat/validator.py` | plan validation/repair and answer validation |
| `mofchat/tools.py`, `mofchat/optimizer.py` | SQL executor, closest-match fallback, NSGA-II |
| `mofchat/ft_transformer.py`, `mofchat/similarity.py` | FT-Transformer (regressor + masked autoencoder), similarity search |
| `mofchat/properties.py` | property prediction + SHAP at runtime |
| `mofchat/knowledge.py`, `knowledge/` | RAG retrieval and the curated knowledge notes |
| `setup_db.py`, `setup_vectorstore.py`, `train_ft.py`, `train_property_models.py` | build steps |
| `evaluate.py`, `benchmark/` | 64-question development benchmark + 20-question held-out set |
| `tests/` | 26 unit tests (`python -m pytest -q`) |
| `docs/` | report, results, literature review, viva guide |
| `agent_core.py` | compatibility shim for the review-1 scripts |

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

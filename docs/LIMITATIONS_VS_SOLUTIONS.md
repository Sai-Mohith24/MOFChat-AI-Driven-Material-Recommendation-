# Base-paper limitations and how MOFChat addresses them

The nine limitations are the ones listed for ChatMOF (Kang & Kim, *Nat. Commun.* 2024) on slide 4 of the review-1 deck. "Evidence" points to code and to measured results in [RESULTS.md](RESULTS.md).

| # | ChatMOF limitation | What MOFChat does | Status | Evidence |
|---|---|---|---|---|
| 1 | No intrinsic materials knowledge: the LLM only plans tool calls | RAG over curated, referenced notes (dataset definitions, kinetic diameters, application heuristics, MOF basics) and the ChatMOF paper; Sentence-BERT + FAISS with an off-topic threshold | Done | `knowledge/`, `setup_vectorstore.py`, `mofchat/knowledge.py`; knowledge-retrieval metrics in RESULTS §3 |
| 2 | Token-context limits: 4 % of ChatMOF search tasks failed with "token limit exceeded" | SQL filters all 12,020 MOFs before the LLM sees anything; the answer writer receives at most 10 verified rows | Done | `mofchat/tools.py`; average prompt stays small regardless of match count (e.g. 206 matches → 3 rows) |
| 3 | Reasoning and logic errors from LLM-written code | The LLM writes a JSON **plan**, never code. The validator checks columns, operators, units, physical ranges and grounding, sends errors back for up to 2 self-corrections, then falls back to the rule parser. SQL is compiled from a whitelist with bound parameters on a read-only connection | Done | `mofchat/validator.py`, `mofchat/agent.py::plan`; single-shot vs validated LLM in RESULTS §1 |
| 4 | Restricted search space (about 100 parent structures due to tokens) | Every query searches the full 12,020-MOF table; NSGA-II ranks all candidates (all 12,020 MOFs: 0.02 s with two objectives, 2.6 s with three) | Done (for screening existing MOFs) | `mofchat/optimizer.py`; `tests/test_core.py::test_non_dominated_sort_matches_brute_force` |
| 5 | Narrow topology coverage (9 topologies in generation) | MOFChat recommends from all experimentally reported CoRE-MOF structures (65 metals, all topologies in the table) | Done for recommendation; MOFChat does not generate new structures | `data/coremof.db` |
| 6 | Needs a dedicated pretrained model per property | Surrogate models are trained directly on the table for any column (surface area, void fraction), with a model comparison | Done for properties in the table; gas uptake is impossible without uptake data | `train_property_models.py`; RESULTS §4 |
| 7 | General, non-fine-tuned LLM | Domain prompts, few-shot planning examples, transparent application presets with rationale, and grounding in data. The LLM is not fine-tuned | Partly (no fine-tuning) | `mofchat/llm.py`, `mofchat/config.py::APPLICATIONS` |
| 8 | High compute cost (GA + simulations) | Millisecond geometric screening plus ML surrogates (XGBoost trains in 0.25 s and predicts in milliseconds); no simulations required | Done | `train_property_models.py` timings in `artifacts/property_models/metrics.json` |
| 9 | Unvalidated output quality | (a) Answer validator: MOF IDs and numbers must match the results; garbled IDs corrected; regenerate or flag. (b) Calibrated uncertainty: split-conformal 90 % intervals (≈ 90 % coverage on test). (c) Explanations: SHAP per prediction, a percentile "why" per recommendation, Pareto plots, FT-Transformer attention. (d) A labelled benchmark with a held-out set | Done | `mofchat/validator.py::validate_answer`, RESULTS §1–§4 |

## What is still out of scope

- **Gas uptake and selectivity prediction.** The local data has geometry only; the hMOF folder contains structures and energy grids but no uptake labels. A next step is to attach hMOF/CoRE GCMC uptake data, then train the same surrogate pipeline on it.
- **Structure generation.** ChatMOF's genetic algorithm creates new MOFs with PORMAKE; MOFChat only recommends existing ones.
- **Stability, synthesis conditions and cost** are not in the dataset. MOFChat says so in its knowledge notes and caveats.

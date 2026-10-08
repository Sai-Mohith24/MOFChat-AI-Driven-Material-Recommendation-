# Viva guide: MOFChat (final version)

Numbers below come from [RESULTS.md](RESULTS.md), which `evaluate.py` generates. If you rerun the evaluation, check them again.

## 0. Headline numbers (from RESULTS.md)

| What | Number |
|---|---|
| Review-1 two-tower vs final hybrid, exact answers (64-question development set) | 9.4 % → 100 % (the rule parser was tuned on this set) |
| Same, held-out set (20 new phrasings, never tuned on) | 5 % → 80 % exact; 41.8 % → 90.9 % constraint precision |
| Llama 3 single shot → + validator → hybrid (development / held-out) | 85.9 → 93.8 → 100 % / 65 → 70 → 80 % |
| Answer drafts with an unverifiable MOF ID or number | 0 of 16; mean 5.8 s per full answer |
| Surface-area surrogate (XGBoost) | R² 0.982, MAE 90 m²/g; 90 % conformal interval covers 90.5 % |
| FT-Transformer regressor / Gaussian process | R² 0.9815 / 0.977 |
| Physics rule (surface area = 0 if PLD < 3.31 Å) | 100 % on test |
| Knowledge retrieval | hit@3 83%; off-topic rejected 100% |
| Unit tests | 26 passing |

## 1. The project in 30 seconds

MOFChat lets a materials scientist ask in plain English for metal-organic frameworks and get **verifiably correct** answers from the 12,020-MOF CoRE-MOF table (the table used by ChatMOF).

1. A local Llama 3 turns the question into a structured plan.
2. A validator checks the plan.
3. SQL retrieves exact matches; NSGA-II ranks them when there are several objectives.
4. ML surrogates predict properties, with SHAP explanations and calibrated intervals.
5. Llama 3 writes the explanation, and an answer validator rejects any MOF ID or number that is not in the results.

## 2. What changed after review 1, and why (expect this question)

- **Review-1 design:** embed the question with Sentence-BERT (384-d), embed each MOF with an FT-Transformer autoencoder (384-d), and match them by cosine similarity in FAISS ("two-tower").
- **Problem we found:** the two towers were never trained together. Equal dimensions do not make two vector spaces comparable, so a real two-tower model needs contrastive training on (question, matching MOF) pairs.
- **Evidence:**
  - "surface area > 4000 and void fraction > 0.8" returned 100 MOFs with a maximum surface area of 807, although 206 MOFs satisfy it.
  - "recipe for chocolate cake" returned the identical 100 MOFs.
  - On our 64-question benchmark the review-1 system gets **9.4 %** exact answers, and only about 30 % of the MOFs it returns satisfy the constraints.
- **Fix:** numeric constraints are facts, so they are evaluated exactly (SQL). The LLM does what it is good at, understanding language, and outputs a plan instead of answers. The FT-Transformer is kept where it is valid: MOF-to-MOF similarity (both sides in the same space) and property prediction.
- **How to say it:** "We tested our own first design, measured that it failed, found the cause, and replaced it. The benchmark that shows the failure is part of the project."

## 3. Likely questions and answers

**Q: Why not let the LLM write SQL directly, like ChatMOF writes pandas code?**
ChatMOF's own error analysis lists logic errors and token-limit failures from generated code. A JSON plan is much smaller and can be checked field by field: column names come from a whitelist, values are bound parameters, and the connection is read-only. Injection or a wrong column becomes impossible, and validation errors go back to the LLM for self-correction.

**Q: What does the validator check?**
- Unknown columns and operators (with alias resolution, e.g. "porosity" → void fraction).
- Non-numeric values and percentages (80 % → 0.8).
- Physically impossible values: an invented one is an error; one the user typed is kept with a note.
- Thresholds that do not appear in the question. If the LLM invents "surface area > 3000" for "high surface area", that becomes an objective instead of a filter.
- MOF IDs not mentioned in the question, and contradictory bounds.
- A common Llama 3 slip, "lowest X" written as a constraint without a value, is repaired into an objective.

**Q: What is the hybrid planner?**
The LLM plan plus facts the deterministic parser is certain about: explicit numbers, metals, limits, and an application named by keyword. Compare the rows in RESULTS §1: single-shot LLM vs LLM + validator vs hybrid. The held-out set (20 questions written after tuning) measures generalisation honestly.

**Q: Explain NSGA-II and why you use it.**
With two or more objectives (e.g. high surface area and low density) there is no single best MOF, only trade-offs.
1. Non-dominated sorting splits candidates into Pareto fronts. Front 1 holds the MOFs that no other MOF beats in every objective.
2. Within a front, crowding distance prefers MOFs in sparse regions, so the user sees diverse trade-offs.

We use NSGA-II's selection operator because we rank existing MOFs rather than evolving new ones. For two objectives the front is found exactly with an O(n log n) sweep; all 12,020 MOFs take 0.02 s. Before sorting, MOFs in the worst 25 % of any objective are screened out, because NSGA-II always keeps extreme points (e.g. smallest pores but almost no surface area).

**Q: What does the FT-Transformer do now?**
- **Similarity search.** A masked-descriptor autoencoder: 30 % of descriptor tokens are replaced by [MASK] and the [CLS] state must reconstruct all ten descriptors. The [CLS] embedding powers "MOFs similar to X". Its neighbours are almost as close in descriptors as a plain k-NN (0.077 vs 0.068 σ, random 0.95 σ) and match metal type more often (27.8 % vs 22.8 %).
- **Property regression.** It predicts surface area with R² 0.9815, essentially tied with XGBoost (0.9818). That matches Grinsztajn et al. (NeurIPS 2022): trees are still very strong on medium-sized tabular data.

**Q: Why XGBoost + SHAP for prediction?**
- XGBoost is the most accurate and fastest model (R² 0.982, MAE 90 m²/g, trains in 0.25 s).
- TreeSHAP gives exact Shapley values, which explain each prediction feature by feature.
- Pore volume and void fraction dominate the surface-area prediction, which is physically sensible: more accessible void means more accessible wall.

**Q: What is the physics rule?**
The descriptors were computed with a 3.31 Å probe. If the pore limiting diameter is smaller than the probe, nothing is accessible, so surface area = 0. It holds for 100 % of the test set (one borderline MOF in training). It does not improve XGBoost's accuracy, because XGBoost learns it, but it makes zero predictions exact and explainable.

**Q: How do you know the prediction intervals are right?**
They come from split-conformal prediction. The 90 % half-width is the 90th percentile of absolute errors on a separate calibration split. On the untouched test split, 90.5 % of true values fall inside (target 90 %). The Gaussian process gives its own 95 % intervals, with 93.9 % coverage.

**Q: What is Gaussian process regression doing here?** (Lecture 5)
- It is a Bayesian non-parametric regressor with an RBF kernel (one length scale per feature, ARD) plus a noise term, giving a mean and an uncertainty.
- It is trained on 2,000 MOFs because exact GPR costs O(n³).
- It reaches R² 0.977, close to XGBoost, with calibrated uncertainty.

**Q: What is RAG in your system?**
Two kinds of retrieval feed the generator:
1. **Structured retrieval:** SQL over the MOF table.
2. **Text retrieval:** Sentence-BERT + FAISS over 102 chunks (curated notes with references, plus the ChatMOF paper).

Off-topic questions are rejected when the best cosine similarity is below 0.30: 100 % of off-topic test questions are rejected, and the correct source is in the top 3 for 83 % of in-domain questions.

**Q: How do you stop hallucination?**
1. The LLM never sees more than the verified rows.
2. The answer validator extracts every MOF-ID-like token and every number from the answer. IDs must be in the results; near-misses such as ACOCLUS → ACOCUS are corrected automatically. Numbers must match the table, the question or a known constant (within rounding).
3. On failure the answer is regenerated once with the exact problems listed. Anything still unverifiable is flagged in the UI, and the true table is always shown.

**Q: Data preprocessing: what did you find?**
- No missing values or duplicate rows.
- Two columns are exact duplicates and were dropped.
- Pore volume = void fraction / density exactly, so it carries no new information. It was one of the four review-1 FT inputs.
- 27 % of MOFs have zero surface area; that is real (probe exclusion), not missing data.
- The density header says cm³/g, but the values are g/cm³.
- 2,087 MOFs contain several metals, so we built a separate metal table for exact filtering.

**Q: Limitations?**
- No adsorption data, so application recommendations are geometric heuristics, not uptake predictions.
- Recommendation only, no structure generation.
- The LLM still mis-plans some phrasings (see the held-out errors in RESULTS).
- Llama 3 8B is small; a full answer takes about 5.8 s on average locally.

**Q: Your literature review: are the papers real?**
The review-1 table had problems: six of the fifteen papers do not exist, and several had wrong authors. For example, ChatMOF is by Y. Kang and J. Kim, not A. S. Rosen. We verified every entry and replaced the table ([LITERATURE_REVIEW.md](LITERATURE_REVIEW.md)). Say this openly if asked.

## 4. Demo script (5 minutes)

1. Chat: *"Find me 3 MOFs with a surface area greater than 4000 and a void fraction greater than 0.8"*. Open "How this answer was produced" to show the plan, SQL and validator.
2. Chat: *"Which zinc MOFs have high surface area and low density?"*. Open the Pareto plot (NSGA-II).
3. Chat: *"Recommend MOFs for CO2 capture"*. Point out the heuristic note, sources and caveats.
4. Chat: *"MOFs with surface area above 20000"*. It says none exist and shows the closest ones.
5. Predict & explain: enter descriptors and show the prediction, interval, SHAP bars and FT attention.
6. Evaluation page: benchmark table (review-1 vs final system), parity plots, SHAP summary.

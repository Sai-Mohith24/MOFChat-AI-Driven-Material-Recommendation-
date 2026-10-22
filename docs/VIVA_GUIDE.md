# Viva guide: MOFChat (final version)

Numbers below come from [RESULTS.md](RESULTS.md), which `evaluate.py` generates. If you rerun the evaluation, check them again.

## 0. Headline numbers (from RESULTS.md)

| What | Number |
|---|---|
| Review-1 two-tower vs final hybrid, exact answers (64-question development set) | 9.4 % → 100 % (the rule parser was tuned on this set) |
| Same, held-out set (20 new phrasings, never tuned on) | 5 % → 100 % exact with the default model (Gemini 3.1 Flash-Lite); 80 % fully offline with Llama 3; rules alone 80 % |
| Model comparison, held-out hybrid | Flash-Lite 100 %, GPT-OSS 120B / Qwen 3.8 / Nemotron 95 % (all miss only the same arguable question), Llama 3 80 %; Gemini 3.5 Flash ran out of free quota |
| Llama 3 single shot → + validator → hybrid (development / held-out) | 85.9 → 93.8 → 100 % / 65 → 70 → 80 % (the safety layers matter most for the small local model) |
| Answer drafts with a problem (16 per model) | Flash-Lite 0; Llama 3 2 (fixed on rewrite); GPT-OSS 120B 2 (one false "Pareto front 1" claim still flagged); about 10 s per full answer |
| Surface-area surrogate (XGBoost) | R² 0.982, MAE 90 m²/g; 90 % conformal interval covers 90.5 % |
| FT-Transformer regressor / Gaussian process | R² 0.9815 / 0.977 |
| Physics rule (surface area = 0 if PLD < 3.31 Å) | 100 % on test |
| Knowledge retrieval | hit@3 83%; off-topic rejected 100% |
| Unit tests | 38 passing |

## 1. The project in 30 seconds

MOFChat lets a materials scientist ask in plain English for metal-organic frameworks and get **verifiably correct** answers from the 12,020-MOF CoRE-MOF table (the table used by ChatMOF).

1. A language model turns the question into a structured plan. It can be a free cloud model (Gemini, Groq, OpenRouter) or a local one (Llama 3 through Ollama); if one is rate-limited, the next one takes over.
2. A validator checks the plan.
3. SQL retrieves exact matches; NSGA-II ranks them when there are several objectives.
4. ML surrogates predict properties, with SHAP explanations and calibrated intervals.
5. The LLM writes the explanation, and an answer validator rejects any MOF ID, number or comparison claim that the results do not support.

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
- For an application question ("best MOFs for CO2 capture"), ranking objectives the question does not mention are dropped, so the CO2 preset decides the ranking. We found this while testing the app with GPT-OSS 20B.

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
2. **Text retrieval:** Sentence-BERT + FAISS over 104 chunks (curated notes with references, plus the ChatMOF paper).

Off-topic questions are rejected when the best cosine similarity is below 0.30: 100 % of off-topic test questions are rejected, and the correct source is in the top 3 for 83 % of in-domain questions.

**Q: How do you stop hallucination?**
1. The LLM never sees more than the verified rows.
2. The answer validator extracts every MOF-ID-like token and every number from the answer. IDs must be in the results; near-misses such as ACOCLUS → ACOCUS are corrected automatically. Numbers must match the table, the question or a known constant (within rounding).
3. It also checks comparison claims. GPT-OSS 20B once wrote that three Zn MOFs "offer surface areas ≥ 6000 m²/g" when one had 4,564: every number existed somewhere in the results, so a number check alone passes it. The validator finds the property from the unit, the MOFs from the IDs in the sentence (or "these", "all five"), and checks each against the database; "first Pareto front" claims are checked against the NSGA-II ranks.
4. On failure the answer is regenerated once with the exact problems listed. Anything still unverifiable is flagged in the UI, and the true table (or the prediction card) is always shown.

What it does not check: free-text reasoning. A small model can still write a wrong formula or definition in a sentence without numbers; the knowledge sources are shown so the user can verify.

**Q: Which language model do you use, and why that one?**
We compared six free models on both question sets with fallback switched off (RESULTS §1b). Gemini 3.1 Flash-Lite answered all 20 held-out questions exactly; GPT-OSS 120B, Qwen 3.8 27B and Nemotron 3 Super answered 19, and all three missed the same question ("Is there any MOF with density above 8 g/cm³?"), which they answered with a count of 0, arguably also correct. So the cloud models are effectively tied on accuracy and differ in free-tier reliability and speed. The default order is Flash-Lite, then GPT-OSS 120B (zero provider errors, a different provider), then Qwen 3.8, then local Llama 3 for offline use. Be honest about Gemini 3.5 Flash: its daily free quota ran out during the run, so it has no score.

**Q: Why keep the validator if a cloud model already gets 100 %?**
Three reasons: it costs nothing for a strong model (100 → 100 %, under 0.01 s); it is what makes the offline 8B model usable (65 → 80 % on held-out questions); and free tiers have bad days (quota exhaustion, overload), when the app falls back to a weaker model or the rule parser.

**Q: What happens when a free model is rate-limited or down?**
Every call goes through one function that knows each model's free-tier budget (requests per minute, Groq's 8,000 tokens per minute) and waits or skips accordingly. On a 429/503 it moves to the next model in the fallback chain; if every model fails, the rule parser plans and a template writes the answer. The app shows which model actually answered. In the evaluation, fallback is switched off so that every score belongs to exactly one model.

**Q: What did you find when you tested the finished app?**
Four bugs, all fixed with a unit test each:
1. A false comparison claim ("≥ 6000 m²/g") passed the number check, so the validator now checks comparisons and Pareto-front claims.
2. GPT-OSS 20B replaced the CO2-capture preset with its own objectives, so the explanation described a ranking that was not used. The validator now drops objectives the question does not mention.
3. A prediction question got no prediction: the validator flagged "90 %" (the interval level) as unverified, and the rewrite request made the model refuse to quote the prediction. The interval level is now a known constant, the prompt says how to report predictions, and the chat always shows a prediction card.
4. GPT-OSS writes thousands with narrow spaces ("8 318"), which the number check split into "318". It now reads them as one number.

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
- The small local model still mis-plans some phrasings (PROJECT_REPORT §5.1 lists them); the cloud models miss at most one held-out question.
- Offline, Llama 3 8B reaches 80 % on held-out questions (cloud models 95–100 %); a full answer takes about 9 s on a laptop.
- Free tiers have quotas and bad days: Gemini 3.5 Flash ran out of its daily quota during our evaluation and Qwen 3.8 hit Groq's limits on 7 of 16 answers. The fallback chain hides this from the user but it limits how much we can test.

**Q: Your literature review: are the papers real?**
The review-1 table had problems: six of the fifteen papers do not exist, and several had wrong authors. For example, ChatMOF is by Y. Kang and J. Kim, not A. S. Rosen. We verified every entry and replaced the table ([LITERATURE_REVIEW.md](LITERATURE_REVIEW.md)). Say this openly if asked.

## 3b. Questions a materials-modelling examiner is likely to ask

**Q: Can MOFChat predict CO2 (or H2, CH4) uptake?**
No, and say so directly. The CoRE-MOF table we use has geometry only (pore sizes, surface area, void fraction, density, metals); it has no adsorption isotherms. Uptake needs either GCMC simulation (grand canonical Monte Carlo with force fields such as UFF/TraPPE) or experimental data. What we do instead is rank by geometric proxies that the literature links to uptake (surface area and void fraction for storage, open metal sites and narrow pores for CO2) and label these as heuristics in the app. The next step is to attach GCMC uptake labels (e.g. from hMOF or CoRE-MOF simulation sets) and train the same surrogate pipeline on them.

**Q: Where does "simulation" appear in your project?**
- The descriptors themselves are simulation outputs: Zeo++ computes pore diameters, surface area and volumes by probing the crystal with a 3.31 Å (N2-sized) sphere.
- Our surrogate models replace those calculations: XGBoost predicts surface area from cheap descriptors in milliseconds (R² 0.982).
- The physics rule (PLD below the probe diameter → zero accessible area) comes straight from how the simulation works.

**Q: Why is surface area exactly zero for 27 % of the MOFs? Isn't that bad data?**
No. Those MOFs have a pore limiting diameter below the 3.31 Å probe, so the probe cannot enter; their accessible area is zero by definition. Every one of the 3,252 zero-area MOFs satisfies this, and the rule classifies the test set with 100 % accuracy.

**Q: Explain LCD, PLD and why PLD matters for separation.**
LCD (largest cavity diameter) is the largest sphere that fits anywhere in the pore network; PLD (pore limiting diameter) is the largest sphere that can pass through it, i.e. the narrowest window. Separation by size (molecular sieving) depends on PLD: to pass CO2 (kinetic diameter 3.3 Å) but block N2 (3.64 Å), PLD must lie between them. The separation preset uses exactly that rule.

**Q: Why are open metal sites good for CO2 capture?**
An open (coordinatively unsaturated) metal site is a metal atom with an empty coordination position facing the pore. CO2's quadrupole and its oxygen lone pairs interact strongly with it, raising adsorption enthalpy and CO2/N2 selectivity (HKUST-1 and Mg-MOF-74 are the classic examples). That is why the CO2 preset requires an open metal site.

**Q: Your 100 % accuracy looks suspicious.**
- The development-set 100 % is optimistic for the rule parser because it was tuned on those questions; we say so.
- The honest number is the held-out set: 20 phrasings written after tuning, never used to tune anything. The default model gets 20/20; the offline model 16/20.
- 20 questions is small (one question = 5 points), so we report the per-model comparison and the ablation to show the result is not luck.
- 100 % means the system returns exactly the same MOFs as a hand-written gold plan, which is a strict criterion.

**Q: What changed since review 1?**
The review-1 retrieval (Sentence-BERT question vector searched against FT-Transformer MOF vectors) did not depend on the question, scoring 9.4 % on our benchmark. We replaced it with plan → validate → SQL/NSGA-II and kept the FT-Transformer for MOF-to-MOF similarity and prediction. We also corrected the literature table: six review-1 references could not be found anywhere and were removed; the new review lists only papers verified against publisher or arXiv records.

**Q: Why trust a geometric heuristic like Chahine's rule?**
Chahine's rule is an empirical observation that H2 uptake at 77 K scales with surface area (about 1 wt % per 500 m²/g). It is a screening rule, not a prediction; we use it only to rank candidates and state it as such.

**Q: Where are accuracy, ROC-AUC and confusion matrices? Your models are regressors.**
Correct: surface area and void fraction are regression tasks, so we report R², MAE and RMSE for them. For classification metrics we evaluated the real classification tasks in the project ([DL_RESULTS.md](DL_RESULTS.md), `evaluate_dl.py`):
- **Open-metal-site prediction:** a deep-learning classification experiment on a real database label. FT-Transformer 0.728 accuracy / 0.755 ROC-AUC, MLP 0.734 / 0.756, XGBoost 0.750 / 0.787, against a majority baseline of 0.663 / 0.50.
- **Planner intent classification:** 0.988 accuracy for the hybrid planner.
- **Off-topic detection:** ROC-AUC 0.981.

We did not invent a classification task with a made-up label.

**Q: Why does XGBoost beat your deep models again?**
On medium-sized tables with a handful of features, gradient-boosted trees are usually as good as or better than neural networks. Grinsztajn et al. (NeurIPS 2022) show this, and TabM (ICLR 2025) and TabPFN (Nature 2025) are recent attempts to close the gap. Our results agree:
- in regression the FT-Transformer ties XGBoost;
- in OMS classification it is 3 AUC points behind and overfits less (train / test accuracy 0.781 / 0.728 vs 0.868 / 0.750).

**Q: What do the learning curves show?**
Train loss keeps falling while validation loss flattens and then rises, which is the onset of overfitting. Early stopping keeps the epoch with the lowest validation loss: FT-Transformer epoch 31 for OMS, 138 for surface area. The green dashed line is the untouched test score.

## 3c. Demo-day checklist

1. Run the app on the laptop you will present from, the day before: `venv/bin/streamlit run app.py --server.port 8502`.
2. Start the offline fallback first: `ollama serve` (Llama 3 must be listed by `ollama list`).
3. Check internet and that the sidebar shows "LLM: Gemini 3.1 Flash-Lite, 10 of 14 models ready" or similar.
4. Each answer takes about 10–50 s on free tiers (planning + retrieval + answer + validation). Ask the next question while explaining the previous one, or pre-run the five demo questions so the answers are already on screen.
5. Use the default cloud model for the prediction question: the offline Llama 3 sometimes names invented MOFs in prediction answers (the validator now flags them, but it looks bad live).
6. If the network fails: switch the sidebar to Llama 3 (local), or to "rules" planner with no language model; both work offline.
7. Backup: the deck's appendix has screenshots of real answers.

## 4. Demo script (5 minutes)

0. Sidebar: open "All language models" to show the 14 models and which are ready; the default model is selected.
1. Chat: *"Find me 3 MOFs with a surface area greater than 4000 and a void fraction greater than 0.8"*. Open "How this answer was produced" to show the plan, SQL and validator, and the "Answered with" line.
2. Chat: *"Which zinc MOFs have high surface area and low density?"*. Open the Pareto plot (NSGA-II).
3. Chat: *"Recommend MOFs for CO2 capture"*. Point out the heuristic note, sources and caveats.
4. Chat: *"MOFs with surface area above 20000"*. It says none exist and shows the closest ones.
5. Chat: *"Predict the surface area of a MOF with density 0.6, void fraction 0.75, LCD 11 Å, PLD 7 Å"*. The prediction card shows the value, the 90 % interval, the FT-Transformer second opinion and SHAP.
6. Predict & explain: enter descriptors and show the prediction, interval, SHAP bars and FT attention.
7. Evaluation page: benchmark table (review-1 vs final system), the model comparison, parity plots, SHAP summary.

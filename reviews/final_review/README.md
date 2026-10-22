# Final review

- **Slides:** 16 slides with speaker notes, kept as a Claude Slides artifact: https://claude.ai/artifact/DsfL5gw6VXrtaLc89YmYm5 (private until shared from its Share menu; Export there gives PPTX or PDF).
- **`deck_source/`:** a copy of the slide files (`deck.json` plus one HTML file per slide) as published, for version control.
- **Numbers:** every number on the slides comes from [docs/RESULTS.md](../../docs/RESULTS.md) (evaluation of 2026-10-08). If the evaluation is re-run, check the benchmark, model-comparison and answer-validation slides again.
- **Demo:** the last slide lists the five demo questions; [docs/VIVA_GUIDE.md](../../docs/VIVA_GUIDE.md) has the full demo script and likely questions.

## PowerPoint deck (updated 2026-10-22)

- **`MOFChat_Final_Review.pptx`**: 36 slides (34 + 2 appendix), built in the style of the review-1 template (A4 landscape, Amrita logo, blue heading bars, Arial). All body text, tables, diagrams and charts use one size (12 pt); titles are 24 pt. `MOFChat_Final_Review.pdf` is the same deck exported from PowerPoint.
- **Contents:**
  - 18 verified 2024–2026 papers and the research gap;
  - feature-extraction graphs;
  - dashboard-to-backend pipeline, offline/online pipeline, two slides explaining how each model works, FT-Transformer architecture;
  - benchmark results and open-metal-site classification (accuracy, ROC-AUC, confusion matrices, train/val/test curves);
  - regression results with learning curves, intent and off-topic classification, explainability;
  - app screenshots, conclusion and references.
- **`pptx_source/`**: the generator (`build.js`, pptxgenjs) and its images. Numbers are read at build time from `artifacts/` (written by `evaluate.py` and `evaluate_dl.py`).
- **Rebuild:** `npm install pptxgenjs sharp`, then run `PPTX_SKILL=<pptx skill dir> node build.js` from `pptx_source/`.

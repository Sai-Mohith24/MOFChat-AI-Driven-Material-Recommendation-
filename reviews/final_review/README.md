# Final review

- **Slides:** 16 slides with speaker notes, kept as a Claude Slides artifact: https://claude.ai/artifact/DsfL5gw6VXrtaLc89YmYm5 (private until shared from its Share menu; Export there gives PPTX or PDF).
- **`deck_source/`:** a copy of the slide files (`deck.json` plus one HTML file per slide) as published, for version control.
- **Numbers:** every number on the slides comes from [docs/RESULTS.md](../../docs/RESULTS.md) (evaluation of 2026-10-08). If the evaluation is re-run, check the benchmark, model-comparison and answer-validation slides again.
- **Demo:** the last slide lists the five demo questions; [docs/VIVA_GUIDE.md](../../docs/VIVA_GUIDE.md) has the full demo script and likely questions.

## PowerPoint deck (2026-10-21)

- **`MOFChat_Final_Review.pptx`**: 27 slides with speaker notes, in the order intro → literature → data and method → results → app → conclusion → references. `MOFChat_Final_Review.pdf` is the same deck exported from PowerPoint.
- **`pptx_source/`**: the generator (`build.js`, pptxgenjs) and its images. Numbers come from `docs/RESULTS.md` (evaluation of 2026-10-08); if the evaluation is re-run, update them in `build.js` and rebuild with `npm install pptxgenjs react-icons react react-dom sharp`, then `node build.js`.

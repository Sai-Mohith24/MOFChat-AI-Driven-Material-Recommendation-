# How to run MOFChat

1. **Language models** (optional; the app works without any LLM using its rule-based planner).
   - **Free cloud models:** put your keys in `.env`, copied from `.env.example`. The keys for Gemini, Groq and OpenRouter are already there.
   - **Local models:** open the Ollama app, or run `ollama serve` in a separate terminal.
   - **Check which models are ready:** `python -m mofchat.llm --list`.

2. **Go to the project and activate the environment:**
   ```bash
   cd /Users/saimohith/Documents/Sem-5/Data-Driven/Final-project
   source venv/bin/activate
   ```

3. **First time only, or after changing data or models**, build everything (about 10 minutes):
   ```bash
   python run_pipeline.py
   ```

4. **Run the app:**
   ```bash
   streamlit run app.py
   ```
   It opens at http://localhost:8501 with five pages: Chat, Explore & optimise, Predict & explain, Evaluation, About.

5. **Run the tests and the evaluation:**
   ```bash
   python -m pytest -q
   python evaluate.py
   ```
   The full evaluation compares six models and takes about 1.5–2 hours (free-tier rate limits). Use `python evaluate.py --no-llm` for a quick run without any LLM, or `--only answers|knowledge|models` to re-run one part. The evaluation writes `artifacts/eval/` and `docs/RESULTS.md`.

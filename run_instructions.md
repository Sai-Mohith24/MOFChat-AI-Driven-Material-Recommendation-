# How to run MOFChat

1. **Start Ollama** (optional, but needed for the Llama 3 planner and answer writer). Open the Ollama app, or run this in a separate terminal:
   ```bash
   ollama serve
   ```
   The model must be pulled once with `ollama pull llama3`. Without Ollama, the app still works with its rule-based planner.

2. **Go to the project and activate the environment:**
   ```bash
   cd /Users/saimohith/Documents/Sem-5/Data-Driven/Project-antigravity
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
   Use `python evaluate.py --no-llm` for a quick run without Ollama. The evaluation writes `artifacts/eval/` and `docs/RESULTS.md`.

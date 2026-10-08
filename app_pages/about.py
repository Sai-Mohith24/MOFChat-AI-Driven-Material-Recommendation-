import streamlit as st

st.title("About MOFChat", anchor=False)
st.markdown("""
MOFChat is an explainable, data-grounded assistant for choosing metal-organic frameworks (MOFs).
It answers questions over the **12,020-MOF CoRE-MOF 2019 table** used by ChatMOF (Kang & Kim, *Nat. Commun.* 2024),
works with free cloud LLMs (Google Gemini, Groq, OpenRouter) or fully offline with local Ollama models, and never lets the language model invent data:
every MOF and every number comes from the database, and the answer is checked before it is shown.
""")

st.subheader("Architecture", anchor=False)
st.mermaid_chart("""
graph TD
    Q[User question] --> P{{Planner<br/>LLM JSON plan: Gemini / Groq /<br/>OpenRouter / local Ollama<br/>+ rule-based parser}}
    P --> V[Validator<br/>columns, units, ranges,<br/>grounded numbers & IDs]
    V -->|errors: retry up to 2x| P
    V --> X{Intent}
    X -->|search / count| S[(SQLite<br/>parameterised, read-only)]
    S --> N[NSGA-II ranking<br/>Pareto fronts + crowding]
    S --> R[Closest-match fallback<br/>when nothing qualifies]
    X -->|similar| E[FT-Transformer embeddings<br/>+ FAISS cosine search]
    X -->|predict| M[XGBoost surrogate + conformal interval<br/>FT-Transformer second opinion]
    X -->|knowledge| K[RAG: curated notes + ChatMOF paper<br/>Sentence-BERT + FAISS]
    N --> A[LLM answer writer<br/>with automatic model fallback]
    R --> A
    E --> A
    M --> A
    K --> A
    M --> SH[SHAP explanation]
    A --> AV[Answer validator<br/>IDs & numbers must match results]
    AV --> U[Answer + verified table + plan/SQL trace]
""", width="stretch")

st.subheader("How it improves on the base paper (ChatMOF)", anchor=False)
st.markdown("""
| ChatMOF limitation | What MOFChat does |
|---|---|
| Token limits when tables are large (4 % of search tasks failed) | The database is filtered by SQL; the LLM only sees the final ≤ 10 rows. |
| Logic errors from LLM-written code | The LLM writes a JSON plan, never code; a validator checks it and asks for corrections; SQL is compiled from a whitelist. |
| Proprietary GPT-4, online | Free models: Gemini, Groq (GPT-OSS, Qwen), OpenRouter (Nemotron) or local Ollama (offline). Rate limits trigger automatic fallback to the next model, and there is a deterministic fallback without any LLM. |
| No grounding check of the final answer | Answer validator: MOF IDs and numbers must match the retrieved results, and comparison claims ("all three are above 6,000 m²/g", "on the first Pareto front") must hold for every MOF they name. |
| No multi-objective selection | NSGA-II non-dominated sorting + crowding distance over any two or more properties. |
| No explanations | SHAP for property predictions, percentile "why" for every recommendation, Pareto plots, FT attention. |
""")

st.subheader("Data facts worth knowing", anchor=False)
st.markdown("""
- Descriptors were computed with Zeo++ using a 3.31 Å probe. **Accessible surface area is 0 for all 3,252 MOFs whose pore limiting diameter is below 3.31 Å**; MOFChat uses this as an exact physics rule.
- Two columns of the original spreadsheet are exact duplicates, and **pore volume = void fraction / density** exactly, so it is not independent information.
- The spreadsheet labels density as cm³/g; the values are g/cm³.
- The table has **no gas-uptake data**. Application recommendations (CO2 capture, H2/CH4 storage, separations, catalysis) are transparent geometric screening heuristics, not adsorption predictions.
""")

st.subheader("Team", anchor=False)
st.markdown("Team 09 - 22AIE452 Data Driven Material Modeling and Simulation: Amrutha T (24255), "
            "Charan Tej Reddy Y (24259), Poojitha D (24263), Enku Sai Mohith (24316), Ramu Jahna Bindu (24249).")

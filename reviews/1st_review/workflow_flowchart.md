> **Superseded (October 2026).** This document describes the review-1 design, in which the user's question was embedded with Sentence-BERT and searched directly in the FT-Transformer index. The two towers were never trained to align, and testing showed the retrieval ignores the question: it returned 9.4 % exact answers on the 64-question benchmark, and a 'chocolate cake' query returned the same MOFs as 'surface area > 4000'. The current system and an up-to-date viva guide are described in `../../docs/` (PROJECT_REPORT.md, VIVA_GUIDE.md, RESULTS.md).

# Project Workflow Flowchart

Here is the visual representation of your project's workflow from the raw dataset to the final user dashboard. You can include this flowchart in your presentation or report.

```mermaid
graph TD
    %% Styling
    classDef data fill:#f9f,stroke:#333,stroke-width:2px;
    classDef process fill:#bbf,stroke:#333,stroke-width:2px;
    classDef db fill:#bfb,stroke:#333,stroke-width:2px;
    classDef model fill:#fbf,stroke:#333,stroke-width:2px;
    classDef output fill:#fbb,stroke:#333,stroke-width:2px;

    %% Tower 1: Tabular Data
    subgraph Tower 1: Tabular Data Embedding
        A[CoRE-MOF Dataset<br>Excel File]:::data --> B[Data Optimization<br>Clean & Z-Score Scale]:::process
        B --> C[FT-Transformer<br>Feature Tokenizer + Attention]:::model
        C --> D[(384-D Tabular Vectors)]:::db
    end

    %% Tower 2: Text Query
    subgraph Tower 2: Natural Language Query
        E[User Query on Dashboard<br>'Find high surface area MOFs']:::data --> F[Text Encoder<br>Sentence-BERT]:::model
        F --> G[(384-D Text Vector)]:::db
    end

    %% Retrieval & Synthesis
    subgraph Retrieval & Synthesis
        D --> H{FAISS Vector Search<br>Cosine Similarity}:::process
        G --> H
        H -->|Fetches Top 100 matches| I[Local Llama 3 LLM<br>Contextual Reasoning]:::model
        E --> I
        I --> J[Dashboard Response<br>Final Synthesis & Insights]:::output
    end
```

### Flowchart Breakdown:
1. **Tower 1 (Left Side):** Your offline pipeline. The raw Excel data is cleaned, scaled, and passed through the custom **FT-Transformer** to generate mathematical embeddings of the MOFs.
2. **Tower 2 (Right Side):** Your online pipeline. A user asks a question, and **Sentence-BERT** converts the sentence into an embedding of the exact same size.
3. **Retrieval & Synthesis (Bottom):** **FAISS** instantly compares the vectors to find the closest matches. Those matches are fed into **Llama 3** to generate the final smart response.

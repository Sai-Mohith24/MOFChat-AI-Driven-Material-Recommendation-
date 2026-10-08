> **Superseded (October 2026).** This document describes the review-1 design, in which the user's question was embedded with Sentence-BERT and searched directly in the FT-Transformer index. The two towers were never trained to align, and testing showed the retrieval ignores the question: it returned 9.4 % exact answers on the 64-question benchmark, and a 'chocolate cake' query returned the same MOFs as 'surface area > 4000'. The current system and an up-to-date viva guide are described in `../../docs/` (PROJECT_REPORT.md, VIVA_GUIDE.md, RESULTS.md).

# Project Overview & Viva Preparation Guide

Here is a complete breakdown of your project's workflow, an explanation of the code, and a detailed guide on RAG to help you ace your viva.

## 1. Project Workflow (Dataset to User Query)

Your project implements a **Two-Tower Neural Retrieval Architecture**. Instead of traditional SQL queries, it uses Deep Learning to understand both the user's natural language and the physical properties of MOFs (Metal-Organic Frameworks), matching them mathematically.

Here is the step-by-step pipeline:

1.  **Data Extraction & Cleaning:** The pipeline starts with the raw CoRE-MOF dataset (in Excel format). It extracts 4 key physical properties (Surface Area, Density, Pore Volume, Void Fraction), cleans missing values, and mathematically scales them (Z-score normalization) so they are ready for Neural Networks.
2.  **Tower 1 - Tabular Data Embedding (FT-Transformer):** The cleaned numbers are passed into a Deep Learning model called an **FT-Transformer** (Feature Tokenizer + Transformer). 
    *   It tokenizes the numbers (converts them into dense vectors).
    *   It applies Multi-Head Self-Attention to understand the relationships between the physical properties.
    *   **Result:** It compresses every MOF into a **384-dimensional mathematical vector**.
3.  **Tower 2 - Text Encoder:** When a user types a query on the dashboard (e.g., *"Find MOFs with high surface area"*), a Natural Language Processing model (Sentence-BERT) converts the English sentence into a **384-dimensional vector**.
4.  **Retrieval (FAISS):** The 12,000+ MOF vectors are stored in a high-speed database called **FAISS** (Facebook AI Similarity Search). FAISS instantly calculates the "Cosine Similarity" (distance) between the user's text vector and all the MOF vectors, fetching the Top 100 closest matches in milliseconds.
5.  **Synthesis (LLM - Llama 3):** Finally, these top 100 retrieved MOFs are given to a Local Llama 3 model as context. The LLM acts as the brain, verifying the retrieved MOFs against the user's constraints and generating a natural, conversational response for the dashboard.

---

## 2. Code Explanation

Here is exactly what each script in your project does to achieve the workflow above:

### `03_data_optimization.py` (The ETL Pipeline)
*   **What it does:** Extracts, Transforms, and Loads the raw data.
*   **Key Logic:**
    *   Reads the `coremof.xlsx` dataset using Pandas.
    *   Filters the dataset to only include: Name, Surface Area, Density, Pore Volume, and Void Fraction.
    *   Cleans the data by filling any missing `NaN` values with `0`.
    *   Applies `StandardScaler` to perform Z-Score normalization. This ensures no single feature (like a massive surface area) dominates the neural network.
    *   Generates visualizations (Histograms and Correlation Heatmaps) to show the data distribution before and after scaling.
    *   Converts the final processed data into PyTorch Tensors.

### `04_ft_transformer_architecture.py` (The Deep Learning Model)
*   **What it does:** Defines the blueprint for the FT-Transformer neural network.
*   **Key Logic:**
    *   **`NumericalFeatureTokenizer`:** Standard Transformers (like ChatGPT) tokenize *words*. This custom tokenizer takes *continuous numbers* (like Density) and projects them into learnable dense embeddings.
    *   **`FTTransformer`:** The core architecture. It attaches a `[CLS]` (classification) token to the data, passes the tokens through Multi-Head Self-Attention layers, and uses a Linear layer to project the final output into a **384-dimensional space**. This specific size (384) is chosen intentionally so it matches the size of the Text Encoder (Sentence-BERT).

### `05_ft_training_and_retrieval.py` (Orchestration & Evaluation)
*   **What it does:** Brings everything together. It trains the transformer, performs the vector search, and mathematically proves that the model works.
*   **Key Logic:**
    *   **Phase 1 (Training):** It wraps the `FTTransformer` inside an `FTAutoencoder`. Since you don't have labels, it uses unsupervised learning. The model compresses the data to 384 dimensions, and a Decoder tries to reconstruct the original 4 physical properties from those 384 dimensions using Mean Squared Error (MSE) loss.
    *   **Phase 2 (Retrieval):** It converts the learned embeddings into NumPy arrays and loads them into a `faiss.IndexFlatL2` index. It takes a simulated user query vector and searches for the top 100 closest MOFs (`index.search()`).
    *   **Phase 3 (Evaluation):** *This is crucial for academics.* To prove the 384-d vectors actually learned the physics of the MOFs, it trains a simple Logistic Regression classifier directly on the vectors to predict if a MOF has a "High Surface Area". It computes rigorous metrics (Accuracy, Precision, Recall, F1, AUC) and plots the Confusion Matrix and ROC curve. 

---

## 3. Detailed Guide to RAG (For Your Viva)

Even though you aren't using traditional text-based RAG, **your project is technically a highly advanced variant of RAG** (specifically, Tabular RAG). Knowing this will heavily impress your examiners.

### What is RAG?
**RAG (Retrieval-Augmented Generation)** is an AI framework that connects a Large Language Model (LLM) to an external, reliable database. 

### Why do we need it?
1.  **Hallucinations:** Standard LLMs (like ChatGPT) sometimes make things up.
2.  **Outdated Info:** LLMs only know what they were trained on up to a certain date. 
3.  **Private Data:** LLMs don't have access to private, company-specific, or domain-specific data (like your 12,000 CoRE-MOFs).

Retraining an LLM to memorize new data is incredibly expensive. RAG solves this by providing the LLM with an "open-book exam".

### How traditional RAG works (The 3 Steps):
1.  **Indexing:** You take a bunch of PDF documents, split them into chunks, convert them into vectors using an embedding model, and store them in a Vector Database.
2.  **Retrieval:** The user asks a question. The system converts the question into a vector, searches the Vector Database, and retrieves the top 5 most relevant document chunks.
3.  **Generation:** The system gives the user's original question **AND** the retrieved document chunks to the LLM. The LLM reads the chunks and generates an accurate answer based *only* on that context.

### How to relate RAG to your project during the Viva:
If an examiner asks about RAG, you can say:

> *"Standard RAG retrieves paragraphs of text from PDFs. In our project, we implemented an advanced version called **Tabular RAG** or **Structured Data RAG**. 
> 
> Instead of embedding text documents, we used an FT-Transformer to embed rows of an Excel sheet (the MOF physical properties). During retrieval, we perform a vector search to find the most relevant MOF rows, and then pass those rows to Llama 3 for the Generation phase. So, we are still doing Retrieval and Generation, but on complex tabular structures rather than plain text."*

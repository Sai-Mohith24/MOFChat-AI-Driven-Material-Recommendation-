> **Superseded (October 2026).** This document describes the review-1 design, in which the user's question was embedded with Sentence-BERT and searched directly in the FT-Transformer index. The two towers were never trained to align, and testing showed the retrieval ignores the question: it returned 9.4 % exact answers on the 64-question benchmark, and a 'chocolate cake' query returned the same MOFs as 'surface area > 4000'. The current system and an up-to-date viva guide are described in `../../docs/` (PROJECT_REPORT.md, VIVA_GUIDE.md, RESULTS.md).

# MOFChat: Explainable AI-Driven Conversational Material Recommendation System

## 1. Abstract
The discovery and selection of Metal-Organic Frameworks (MOFs) for specialized applications (e.g., gas storage, carbon capture, and catalysis) requires parsing vast amounts of empirical data. Traditional database querying often restricts researchers to rigid parameters, while standard Large Language Models (LLMs) hallucinate chemical properties due to a lack of grounded scientific data. 

To bridge this gap, this project introduces a Hybrid Retrieval-Augmented Generation (RAG) architecture. By integrating a Deep Learning **Feature Tokenizer Transformer (FT-Transformer)** for rapid, multi-objective property screening alongside a local LLM, we provide a secure, accurate, and conversational AI assistant for materials scientists.

## 2. Problem Statement
1. **Data Overload:** The CoRE-MOF database contains over 12,000 materials with diverse physical properties (Surface Area, Density, Pore Volume, Void Fraction). Manually screening these is time-consuming.
2. **AI Hallucinations:** Commercial AI models (like ChatGPT) invent scientific properties because they rely on generalized internet training rather than verified, domain-specific databases.
3. **Rigid Interfaces:** Traditional SQL databases require strict programming knowledge, creating a barrier to entry for chemists looking for quick material recommendations.

## 3. Project Objectives
- Build an offline, privacy-preserving AI assistant using **Llama 3**.
- Optimize a dataset of 12,020 real MOFs from the CoRE-MOF dataset for rapid retrieval.
- Implement a deep learning model to instantly fetch top material candidates based on user constraints, bypassing traditional SQL bottlenecks.

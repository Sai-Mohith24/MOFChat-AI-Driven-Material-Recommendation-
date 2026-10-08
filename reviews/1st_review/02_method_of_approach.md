> **Superseded (October 2026).** This document describes the review-1 design, in which the user's question was embedded with Sentence-BERT and searched directly in the FT-Transformer index. The two towers were never trained to align, and testing showed the retrieval ignores the question: it returned 9.4 % exact answers on the 64-question benchmark, and a 'chocolate cake' query returned the same MOFs as 'surface area > 4000'. The current system and an up-to-date viva guide are described in `../../docs/` (PROJECT_REPORT.md, VIVA_GUIDE.md, RESULTS.md).

# Method of Approach: Two-Tower Neural Retrieval

## Overview
Instead of relying on a slow, traditional SQL database search (which requires rigid, exact constraints), this project utilizes an advanced Deep Learning approach known as a **Two-Tower Neural Retrieval Architecture**. 

This allows the AI to instantly fetch the top 100 most relevant MOFs out of 12,000+ entries using pure mathematical similarity, significantly reducing latency and allowing for "soft" similarity matching on physical properties.

## The Architecture

### 1. Tower 1: The Text Encoder (Natural Language)
When a user asks a question (e.g., *"Find MOFs with high surface area"*), the sentence is passed through a **Sentence-BERT** model (`all-MiniLM-L6-v2`). This model converts the English sentence into a dense mathematical vector of 384 dimensions.

### 2. Tower 2: The FT-Transformer (Tabular Data)
Tabular data (like Excel sheets containing Surface Area, Density, Pore Volume, and Void Fraction) cannot be easily read by standard text AIs. We implemented an **FT-Transformer** (Feature Tokenizer + Transformer). 
- **Tokenization:** It maps each numerical column into a continuous embedding space.
- **Transformer:** It applies Multi-Head Self-Attention across the numerical features.
- **Output:** It compresses the physical properties of a MOF into a 384-dimensional vector, matching the exact size of the Text Encoder.

### 3. FAISS Vector Search (Retrieval)
We pre-compute the FT-Transformer embeddings for all 12,020 MOFs and store them in a **FAISS** (Facebook AI Similarity Search) index. 
When a query arrives, the system calculates the **Cosine Similarity** between the user's Text Vector and the 12,020 Tabular Vectors. The closest 100 matches are retrieved in milliseconds.

### 4. LLM Synthesis (Llama 3)
The top 100 retrieved MOFs are passed as context to the Local Llama 3 Large Language Model. The LLM acts as the reasoning engine—it mathematically verifies the retrieved materials against the user's constraints and generates a conversational, highly accurate response.

> **Superseded (October 2026).** This document describes the review-1 design, in which the user's question was embedded with Sentence-BERT and searched directly in the FT-Transformer index. The two towers were never trained to align, and testing showed the retrieval ignores the question: it returned 9.4 % exact answers on the 64-question benchmark, and a 'chocolate cake' query returned the same MOFs as 'surface area > 4000'. The current system and an up-to-date viva guide are described in `../../docs/` (PROJECT_REPORT.md, VIVA_GUIDE.md, RESULTS.md).

# 🚀 100% Viva Preparation: Ultimate Study Guide

This guide is designed to make you bulletproof for your viva. Read this front-to-back, and you will have absolute clarity on the project's concepts, architecture, and code.

---

## 📚 PART 1: Core Concepts & Project Architecture

### 1. What is the fundamental problem your project solves?
Traditional databases use SQL (exact matching). If you ask SQL for "MOFs with surface area > 2000", it rigidly filters out an MOF with 1999. It also can't understand natural language. 
**Your solution:** You built a **Two-Tower Neural Retrieval Architecture** that understands the *meaning* of the user's question and mathematically matches it to the *physical properties* of 12,000+ MOFs.

### 2. The "Two-Tower" Architecture Explained
Imagine two people speaking different languages trying to meet in the middle. 
*   **Tower 1 (The MOFs):** An **FT-Transformer** takes the raw numbers (density, surface area, etc.) and translates them into a 384-dimensional mathematical vector (a coordinate in space).
*   **Tower 2 (The User):** A **Sentence-BERT** model takes the user's English sentence and translates it into a 384-dimensional vector in the *exact same space*.
*   **The Meeting Point:** Because both the text and the tabular data are mapped to the same 384-dimensional space, we can measure how close they are using **Cosine Similarity**. 

### 3. What is Tabular RAG?
Retrieval-Augmented Generation (RAG) usually fetches text from PDFs to help an LLM answer questions. 
You are doing **Tabular RAG**. You are retrieving rows of structured tabular data (MOFs) using a deep learning embedding model (FT-Transformer), and giving those rows to Llama 3 to formulate an answer.

---

## 💻 PART 2: The Code Logic (Script by Script)

### Script 1: `03_data_optimization.py` (The ETL Pipeline)
**Goal:** Prepare the raw Excel data for Deep Learning.
1.  **Extract:** Reads `coremof.xlsx` using Pandas.
2.  **Transform:** Keeps only 4 key features (Surface Area, Density, Pore Volume, Void Fraction). Why these 4? Because they physically define the MOF's capacity and structure.
3.  **Clean:** Replaces `NaN` (blank cells) with `0` so the neural network doesn't crash.
4.  **Z-Score Normalization (`StandardScaler`):** Deep learning models hate large numbers. If Surface Area is 3000 and Void Fraction is 0.5, the network will only pay attention to Surface Area. `StandardScaler` shifts all columns to have a mean of 0 and a standard deviation of 1. Now, all features are equally important.
5.  **Load:** Converts the scaled Pandas dataframe into PyTorch Tensors.

### Script 2: `04_ft_transformer_architecture.py` (The Brain)
**Goal:** Build the Neural Network that embeds tabular data.
1.  **`NumericalFeatureTokenizer`:** Standard Transformers (like ChatGPT) tokenize words into vectors. This custom class takes a continuous number (e.g., Density = 1.5) and projects it into a dense embedding vector using learnable weights and biases (`x * weight + bias`).
2.  **`[CLS]` Token:** Just like BERT, you attach a dummy `[CLS]` (Classification) token to the start of the data. As the data passes through the network, this token absorbs the "global meaning" of the entire MOF.
3.  **`TransformerEncoder`:** Applies Multi-Head Self-Attention. It learns how Density interacts with Pore Volume, how Surface Area interacts with Void Fraction, etc.
4.  **Linear Head:** Takes the final `[CLS]` token and projects it down to **384 dimensions**. This size is strictly chosen so it perfectly matches the 384-d output of the Sentence-BERT text encoder.

### Script 3: `05_ft_training_and_retrieval.py` (Execution)
**Goal:** Train the model unsupervised, test retrieval, and evaluate mathematically.
1.  **Phase 1 - Autoencoder Training:** You don't have labeled data (e.g., "Good MOF" vs "Bad MOF"). So how do you train it? **Unsupervised Learning via an Autoencoder**. The model compresses the 4 features into 384 dimensions, and a Decoder tries to reconstruct the original 4 features from the 384. It uses **MSE (Mean Squared Error)** loss. If the reconstruction is accurate, it proves the 384-d vector perfectly captured the physical essence of the MOF.
2.  **Phase 2 - FAISS Retrieval:** Converts embeddings to NumPy arrays and adds them to `faiss.IndexFlatL2`. FAISS calculates L2 distance (which is mathematically proportional to Cosine Similarity when vectors are normalized) and fetches the top 100 closest MOF IDs in milliseconds.
3.  **Phase 3 - Downstream Evaluation:** To prove to academics that the 384-d vectors actually mean something, the script trains a Logistic Regression classifier *purely* on the 384-d vectors to predict if a MOF has a "High Surface Area" (above the median). It plots a **Confusion Matrix** and an **ROC Curve (AUC)**. If the AUC is high, it proves your embeddings are mathematically sound and have successfully learned the physics of the materials.

---

## 🎤 PART 3: Top Viva Questions & How to Answer Them

**Q1: Why did you use an FT-Transformer instead of a standard Neural Network (MLP) or Random Forest?**
> **Answer:** "Standard MLPs treat features independently. The FT-Transformer applies Multi-Head Self-Attention across the numerical features. This allows the model to learn the complex, non-linear relationships between properties—for example, how high void fraction correlates with pore volume. Random Forests are great for classification, but we needed to generate dense vector embeddings to do Cosine Similarity matching with Text, which only a Deep Learning architecture can do."

**Q2: What is Z-Score Normalization and why did you use it?**
> **Answer:** "Z-Score normalization scales all numerical columns to have a mean of 0 and a standard deviation of 1. Neural networks struggle when features have vastly different scales (e.g., Surface Area in thousands vs Void Fraction in decimals). Without scaling, the model would be completely biased toward the larger numbers."

**Q3: How did you train the FT-Transformer if you don't have labels (like Cat vs Dog)?**
> **Answer:** "We used Self-Supervised Learning by wrapping the FT-Transformer inside an Autoencoder. The Encoder compresses the 4 physical properties into a 384-dimensional vector, and the Decoder attempts to reconstruct the original 4 properties. The model learns by minimizing the Mean Squared Error (MSE) between the input and the reconstruction. If it can reconstruct the data, it means the 384-d vector has perfectly captured the MOF's physics."

**Q4: Why exactly 384 dimensions?**
> **Answer:** "The dimensionality must match the output of our Natural Language Text Encoder. We used the `all-MiniLM-L6-v2` Sentence-BERT model for the user's queries, which outputs exactly 384 dimensions. To calculate Cosine Similarity between a text query and a MOF in FAISS, both vectors must exist in the exact same dimensional space."

**Q5: What is FAISS and why not just use a loop to calculate distances?**
> **Answer:** "FAISS stands for Facebook AI Similarity Search. If we used a standard Python loop to calculate Cosine Similarity against 12,020 MOFs, it would be slow, and in a real production environment with millions of rows, it would crash. FAISS is highly optimized in C++ to perform nearest-neighbor searches in milliseconds, making our dashboard real-time."

**Q6: How do you prove your embeddings actually work?**
> **Answer:** "Since Autoencoders don't output a standard 'Accuracy' metric, we performed Downstream Linear Probing. We trained a simple Logistic Regression model using *only* our 384-dimensional vectors to predict a physical property (whether a MOF has high or low surface area). Because the model achieved high Accuracy, Precision, Recall, and a high AUC on the ROC curve, it mathematically proves that our embeddings contain rich, decodable physical meaning."

**Q7: Is this RAG?**
> **Answer:** "Yes, it is a highly advanced variant called Tabular RAG. Standard RAG retrieves chunks of text from PDFs. We use the FT-Transformer to retrieve structured, tabular data (Excel rows). We fetch the top 100 MOFs mathematically, and then feed those tabular rows into Llama 3 as context to generate the final synthesized response."

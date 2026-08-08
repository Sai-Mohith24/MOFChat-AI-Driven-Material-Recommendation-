# MOFChat: AI-Driven Material Recommendation
> **A Hybrid RAG AI assistant that queries 12,000+ Metal-Organic Frameworks to provide accurate, data-driven material recommendations for researchers.**
MOFChat is an advanced, privacy-preserving conversational agent designed to accelerate the discovery and selection of Metal-Organic Frameworks (MOFs) for specialized applications like gas storage, separation, and catalysis. 
Built on a Hybrid Retrieval-Augmented Generation (RAG) architecture, MOFChat seamlessly integrates natural language processing with multi-objective optimization. Unlike standard Large Language Models (LLMs) that hallucinate based on generalized internet data, this system grounds its reasoning in a structured SQLite database containing over 12,000 empirical MOF records (derived from the CoRE-MOF dataset) alongside a FAISS vector store encoding domain-specific materials science rules.
By translating complex user constraints into precise SQL queries, MOFChat dynamically retrieves mathematically accurate material properties and synthesizes them with semantic domain knowledge.
## 🌟 Key Features
- **Fully Offline & Privacy-Preserving:** Powered by local Llama 3 via Ollama, ensuring sensitive research queries never leave your machine.
- **Hybrid RAG Architecture:** Combines structured database querying (SQL) with unstructured semantic search (FAISS Vector Store).
- **Multi-Objective Optimization:** Capable of filtering materials across multiple physical properties simultaneously (e.g., Surface Area, Void Fraction, Pore Volume, Density).
- **Zero Hallucination Retrieval:** Guarantees that recommended MOFs physically exist in the database with accurate CSD Refcodes (e.g., ABUWOJ, UiO-66).
## 🛠️ Technology Stack
- **LLM:** Llama 3 (via Ollama)
- **Orchestration:** LangChain (`langchain`, `langchain-ollama`)
- **Vector Database:** FAISS (`faiss-cpu`)
- **Embeddings:** Sentence-BERT (`all-MiniLM-L6-v2`)
- **Structured Database:** SQLite3 & Pandas
- **Frontend:** Streamlit
## 🚀 Installation & Setup
### 1. Prerequisites
- Python 3.9+
- [Ollama](https://ollama.com/) installed on your machine.
### 2. Clone the Repository
```bash
git clone https://github.com/yourusername/MOFChat.git
cd MOFChat
```
### 3. Create a Virtual Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
### 4. Pull the Local LLM Model
Ensure the Llama 3 model is downloaded and running locally in a separate terminal:
```bash
ollama run llama3
```
### 5. Initialize the Databases

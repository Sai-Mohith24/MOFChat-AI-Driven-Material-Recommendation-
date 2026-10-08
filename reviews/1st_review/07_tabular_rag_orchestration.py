"""
07_tabular_rag_orchestration.py

This script brings the entire Two-Tower architecture together into a Tabular RAG pipeline.
1. It embeds the user's query.
2. It fetches the Top 100 MOFs from the FT-Transformer's FAISS index (Tabular Retrieval).
3. It passes those 100 MOFs into Llama 3 with a strict prompt to synthesize a factual response (Generation).

NOTE (October 2026): kept to document the review-1 design. Its retrieval does not depend on the
question (the text and tabular towers were never trained to align), so it is the "Review-1 two-tower"
baseline in ../../evaluate.py. The current system is ../../mofchat/.
"""

import os
from langchain_ollama import ChatOllama
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# We need a dummy embedding class to load our pre-computed FT-Transformer FAISS index,
# because FAISS usually expects a text embedder, but we did the tabular embedding manually in PyTorch.
class DummyEmbeddings:
    def embed_documents(self, texts): pass
    def embed_query(self, text): pass

def run_tabular_rag(user_query: str):
    print("\n--- Initializing Tabular RAG System ---")
    
    # 1. Load the Models
    llm = ChatOllama(model="llama3", temperature=0)
    text_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    # 2. Load the FAISS Indexes
    # Note: These paths assume you have generated the FAISS indexes from your previous scripts.
    # Adjust paths if they are in the parent directory.
    faiss_ft_path = "../../artifacts/baseline_review1/faiss_ft_index"
    faiss_domain_path = "../../artifacts/knowledge_index"
    
    if not os.path.exists(faiss_ft_path):
        print(f"Error: Could not find FT-Transformer index at {faiss_ft_path}.")
        print("Please ensure your FAISS indexes are generated from the main project folder.")
        return
        
    ft_store = FAISS.load_local(faiss_ft_path, DummyEmbeddings(), allow_dangerous_deserialization=True)
    domain_store = FAISS.load_local(faiss_domain_path, text_embeddings, allow_dangerous_deserialization=True)
    
    print(f"User Query: '{user_query}'\n")
    
    # 3. Retrieval Phase (Tower 1 & 2 Math Matching)
    print("Retrieving Top 100 MOFs using deep vector similarity...")
    query_vector = text_embeddings.embed_query(user_query)
    docs_and_scores = ft_store.similarity_search_by_vector(query_vector, k=100)
    
    # Format the retrieved data into a text block for the LLM
    mof_results = []
    for doc in docs_and_scores:
        metadata = doc.metadata
        mof_results.append(
            f"ID: {metadata['MOF_ID']}, "
            f"Surface Area: {metadata['Surface_Area']:.2f}, "
            f"Density: {metadata['Density']:.4f}, "
            f"Pore Volume: {metadata['Pore_Volume']:.4f}, "
            f"Void Fraction: {metadata['Void_Fraction']:.4f}"
        )
    top_100_context = "\n".join(mof_results)
    
    # Get standard text domain rules
    domain_docs = domain_store.similarity_search(user_query, k=2)
    domain_context = "\n".join([doc.page_content for doc in domain_docs])
    
    # 4. Generation Phase (The LLM Synthesis)
    print("Generating factual response using Local Llama 3...")
    prompt = PromptTemplate.from_template(
        """You are a specialized AI assistant for Metal-Organic Frameworks (MOFs).
        
        A Deep Learning FT-Transformer has retrieved the Top 100 closest MOFs for the user's query. 
        
        DOMAIN KNOWLEDGE:
        {domain_context}
        
        TOP 100 RETRIEVED MOFS:
        {top_100_mofs}
        
        USER QUESTION: {query}
        
        CRITICAL INSTRUCTIONS:
        1. MATHEMATICALLY VERIFY if the retrieved MOFs meet the exact numerical constraints.
        2. Do not invent, round up, or hallucinate data. Be strictly factual.
        3. If no MOF fully matches, state what the closest available MOF is.
        """
    )
    
    chain = prompt | llm | StrOutputParser()
    
    response = chain.invoke({
        "domain_context": domain_context,
        "top_100_mofs": top_100_context,
        "query": user_query
    })
    
    print("\n--- LLM Final Response ---\n")
    print(response)
    print("\n---------------------------\n")

if __name__ == "__main__":
    sample_query = "Find me a MOF that has a Surface Area greater than 4000."
    run_tabular_rag(sample_query)

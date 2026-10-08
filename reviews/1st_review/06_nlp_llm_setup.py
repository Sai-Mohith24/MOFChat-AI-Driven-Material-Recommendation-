"""
06_nlp_llm_setup.py

This script demonstrates the "Tower 2" of our architecture and the LLM initialization.
It shows how we use Natural Language Processing (NLP) to convert a user's English sentence
into a 384-dimensional mathematical vector, and how we connect to the local Llama 3 model.

Note: You must have 'ollama' installed and 'llama3' pulled locally for this to work.
"""

from langchain_ollama import ChatOllama
from langchain_huggingface import HuggingFaceEmbeddings

def test_nlp_and_llm():
    print("--- 1. Initializing NLP Text Encoder (Sentence-BERT) ---")
    # We use 'all-MiniLM-L6-v2' because it specifically outputs a 384-dimensional vector.
    # This exactly matches our FT-Transformer output dimension from Tower 1.
    text_encoder = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    print("Text Encoder Loaded Successfully.")
    
    # Let's test the text embedding
    user_query = "Find me a MOF with high surface area and low density."
    print(f"\nUser Query: '{user_query}'")
    
    query_vector = text_encoder.embed_query(user_query)
    print(f"Generated Vector Length: {len(query_vector)}")
    print(f"First 5 dimensions of the vector: {query_vector[:5]}")
    
    print("\n--- 2. Initializing Local LLM (Llama 3 via Ollama) ---")
    # Temperature=0 ensures the model is factual and does not hallucinate creatively.
    llm = ChatOllama(model="llama3", temperature=0)
    print("Local Llama 3 Connected Successfully.")
    
    print("\nTesting LLM with a simple prompt...")
    test_response = llm.invoke("What does RAG stand for in Artificial Intelligence? Keep it to one sentence.")
    print(f"Llama 3 Response: {test_response.content}")

if __name__ == "__main__":
    test_nlp_and_llm()

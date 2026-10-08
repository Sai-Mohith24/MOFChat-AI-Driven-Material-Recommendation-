from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

def setup_vectorstore():
    """
    Initializes a FAISS vector store with sample MOF domain texts.
    """
    # 1. Define domain knowledge rules as LangChain Documents
    docs = [
        Document(page_content="High surface area (>3000 m2/g) and high void fraction are ideal for CO2 capture applications in Metal-Organic Frameworks."),
        Document(page_content="For methane storage, MOFs with moderate pore volume and high density are often preferred to maximize volumetric capacity."),
        Document(page_content="Water stability in MOFs is generally correlated with stronger metal-ligand coordination bonds and hydrophobic pore surfaces."),
        Document(page_content="MOFs with a density lower than 0.8 g/cm3 typically exhibit higher porosity and larger surface areas."),
        Document(page_content="Hydrogen storage requires materials with extremely high surface areas (>4000 m2/g) and narrow pore size distributions for optimal interaction.")
    ]
    
    print("Loading HuggingFace embeddings (all-MiniLM-L6-v2)...")
    # 2. Initialize HuggingFace Embeddings model (Sentence-BERT)
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    print("Creating FAISS index from documents...")
    # 3. Create FAISS vector store from the documents
    vectorstore = FAISS.from_documents(docs, embeddings)
    
    # 4. Save the vector store locally
    save_dir = "faiss_mof_index"
    vectorstore.save_local(save_dir)
    print(f"Vector store saved successfully to '{save_dir}'.")

if __name__ == "__main__":
    setup_vectorstore()

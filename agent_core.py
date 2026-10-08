import pandas as pd
from langchain_ollama import ChatOllama
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

class MOFHybridAgent:
    def __init__(self):
        # Initialize LLM
        self.llm = ChatOllama(model="llama3", temperature=0)
        
        # Initialize Embeddings for Text (MiniLM)
        self.text_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        # Load the Domain Knowledge FAISS Index (Text Rules)
        self.domain_store = FAISS.load_local("faiss_mof_index", self.text_embeddings, allow_dangerous_deserialization=True)
        
        # Load the DL FT-Transformer FAISS Index (Tabular Embeddings)
        # We pass a dummy embedding function since FAISS.load_local expects one,
        # but we only use it for retrieval using manually generated vectors.
        class DummyEmbeddings:
            def embed_documents(self, texts): pass
            def embed_query(self, text): pass
            
        self.ft_store = FAISS.load_local("faiss_ft_index", DummyEmbeddings(), allow_dangerous_deserialization=True)

    def fetch_top_100_via_dl(self, query):
        """
        Uses the DL Two-Tower approach.
        Embeds the query text and retrieves the top 100 MOFs from the FT-Transformer index.
        """
        # 1. Embed query into 384-dimensional space
        query_vector = self.text_embeddings.embed_query(query)
        
        # 2. Instantly fetch top 100 MOFs from the FT-Transformer Tabular Index
        docs_and_scores = self.ft_store.similarity_search_by_vector(query_vector, k=100)
        
        # 3. Format the top 100 for the LLM
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
        return "\n".join(mof_results)

    def get_domain_context(self, query):
        """Retrieves semantic rules from the domain knowledge FAISS store."""
        docs = self.domain_store.similarity_search(query, k=2)
        return "\n".join([doc.page_content for doc in docs])

    def answer_query(self, query):
        """Main orchestration method for the FT-Transformer Hybrid RAG."""
        
        # 1. DL Retrieval: Fetch Top 100 MOFs via FT-Transformer
        top_100_mofs_context = self.fetch_top_100_via_dl(query)
        
        # 2. Domain Knowledge Retrieval
        domain_context = self.get_domain_context(query)
        
        # 3. LLM Synthesis
        prompt = PromptTemplate.from_template(
            """You are a specialized AI assistant for Metal-Organic Frameworks (MOFs).
            
            A Deep Learning FT-Transformer has retrieved the Top 100 closest MOFs for the user's query. 
            
            DOMAIN KNOWLEDGE:
            {domain_context}
            
            TOP 100 RETRIEVED MOFS FROM DL MODEL:
            {top_100_mofs}
            
            USER QUESTION: {query}
            
            CRITICAL INSTRUCTIONS:
            1. You must MATHEMATICALLY VERIFY if the retrieved MOFs actually meet the exact numerical constraints in the user's question.
            2. If the user asks for a Surface Area > 20000, and the highest retrieved MOF only has 6000, YOU MUST NOT LIE. 
            3. You must explicitly state: "I could not find any MOFs that strictly meet your requirement of [X]. The highest/closest match in the database is [Y]."
            4. Do not invent, round up, or hallucinate data to please the user. Be strictly factual based ONLY on the provided numbers.
            
            Synthesize a helpful, conversational answer following the critical instructions above.
            """
        )
        
        chain = prompt | self.llm | StrOutputParser()
        
        return chain.invoke({
            "domain_context": domain_context,
            "top_100_mofs": top_100_mofs_context,
            "query": query
        })

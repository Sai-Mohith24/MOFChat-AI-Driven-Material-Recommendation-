import sqlite3
import pandas as pd
from langchain_ollama import ChatOllama
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

class MOFHybridAgent:
    """
    Hybrid RAG Agent that queries a FAISS vector store for domain knowledge 
    and a SQLite database for structured MOF properties.
    """
    def __init__(self):
        print("Initializing LLM (llama3)...")
        # Initialize ChatOllama with temperature 0 for factual responses
        self.llm = ChatOllama(model="llama3", temperature=0)
        
        print("Loading local FAISS index...")
        # Load local FAISS index with dangerous deserialization allowed
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.vectorstore = FAISS.load_local(
            "faiss_mof_index", 
            self.embeddings, 
            allow_dangerous_deserialization=True
        )
        
        self.db_path = "hmof.db"

    def query_vector(self, user_input):
        """
        Retrieves the top 2 similar documents from the FAISS index based on the query.
        """
        # Search the vector store and return top 2 documents
        docs = self.vectorstore.similarity_search(user_input, k=2)
        return docs

    def query_sql(self, sql_query):
        """
        Executes a raw SQL query on the hmof.db and returns rows formatted as string.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            # Use Pandas to cleanly execute and read the SQL query
            df = pd.read_sql_query(sql_query, conn)
            conn.close()
            
            if df.empty:
                return "No materials found matching the query."
            return df.to_string(index=False)
        except Exception as e:
            return f"SQL Execution Error: {str(e)}"

    def run(self, user_input):
        """
        Main execution workflow of the Hybrid Agent.
        """
        # Step 1: Retrieve context from the Vector Store (Domain Knowledge)
        docs = self.query_vector(user_input)
        context = "\n".join([f"- {doc.page_content}" for doc in docs])
        
        # Step 2: Use LLM to generate SQL query based on user input
        sql_generation_prompt = f"""
You are an expert SQL generator. The user wants to query a SQLite database.
The database contains a table named 'materials' with the following schema:
MOF_ID (TEXT), Surface_Area (REAL), Density (REAL), Pore_Volume (REAL), Void_Fraction (REAL)

Based on the user's request, generate ONLY a valid SQL SELECT query. 
Do not include markdown tags (like ```sql), do not include comments, and do not explain the query. Just return the raw SQL string.
If the query cannot be answered by this schema, return a generic query: SELECT * FROM materials LIMIT 5;

User Request: {user_input}
SQL Query:
"""
        
        # Try to generate the SQL query robustly
        try:
            sql_response = self.llm.invoke(sql_generation_prompt)
            generated_sql = sql_response.content.strip()
            # Clean up potential markdown blocks if the LLM ignores instructions
            if generated_sql.startswith("```sql"):
                generated_sql = generated_sql[6:]
            if generated_sql.startswith("```"):
                generated_sql = generated_sql[3:]
            if generated_sql.endswith("```"):
                generated_sql = generated_sql[:-3]
            generated_sql = generated_sql.strip()
            
            # Simple safety fallback
            if not generated_sql.upper().startswith("SELECT"):
                generated_sql = "SELECT * FROM materials LIMIT 5;"
        except Exception as e:
            generated_sql = "SELECT * FROM materials LIMIT 5;"
            print(f"Error during SQL generation: {e}")

        # Step 3: Execute the generated SQL query
        sql_results = self.query_sql(generated_sql)
        
        # Step 4: Synthesize final prompt combining original input, FAISS context, and SQLite data
        final_prompt = f"""
You are an expert AI-Driven Conversational Material Recommendation System for Metal-Organic Frameworks (MOFs).
Your task is to recommend MOFs and answer the user's query by analyzing both the retrieved domain knowledge and the structured database results.

User Query: {user_input}

Domain Knowledge (from Vector Store):
{context}

Database Results (SQL Query Used: {generated_sql}):
{sql_results}

Provide a conversational, accurate, and explainable recommendation. Explain why certain MOFs fit the user's needs by connecting the domain knowledge to the data values. If the database results indicate an error or no matches, explain this politely and provide guidance based on the domain knowledge alone.
"""

        # Generate and return final response
        try:
            final_response = self.llm.invoke(final_prompt)
            return final_response.content
        except Exception as e:
            return f"An error occurred while generating the final recommendation: {str(e)}"

# pyrefly: ignore [missing-import]
import torch
# pyrefly: ignore [missing-import]
import torch.nn as nn
# pyrefly: ignore [missing-import]
import torch.optim as optim
import sqlite3
import pandas as pd
from sklearn.preprocessing import StandardScaler
from ft_transformer import FTTransformer, FTAutoencoder
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.documents import Document
import faiss
import os

def train_and_index():
    print("Loading data from hmof.db...")
    conn = sqlite3.connect('hmof.db')
    df = pd.read_sql_query("SELECT * FROM materials", conn)
    conn.close()

    features = df[['Surface_Area', 'Density', 'Pore_Volume', 'Void_Fraction']].values
    mof_ids = df['MOF_ID'].values

    print("Scaling features...")
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features)
    
    # Convert to PyTorch tensors
    X_tensor = torch.tensor(features_scaled, dtype=torch.float32)

    # Initialize model
    print("Initializing FT-Transformer Autoencoder...")
    encoder = FTTransformer(num_features=4, output_dim=384)
    autoencoder = FTAutoencoder(encoder)
    
    optimizer = optim.Adam(autoencoder.parameters(), lr=0.01)
    criterion = nn.MSELoss()

    print("Pre-training the FT-Transformer on tabular features (Self-Supervised)...")
    epochs = 10
    autoencoder.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        embeddings, reconstructions = autoencoder(X_tensor)
        loss = criterion(reconstructions, X_tensor)
        loss.backward()
        optimizer.step()
        if (epoch+1) % 2 == 0:
            print(f"Epoch [{epoch+1}/{epochs}], Loss: {loss.item():.4f}")

    print("Extracting Tabular Embeddings...")
    autoencoder.eval()
    with torch.no_grad():
        embeddings, _ = autoencoder(X_tensor)
        embeddings_np = embeddings.numpy()

    print("Building FAISS Vector Store for top-100 retrieval...")
    dimension = 384
    index = faiss.IndexFlatL2(dimension)
    
    # We must create a LangChain FAISS wrapper. We'll use a dummy embedding function
    # because we are injecting the embeddings directly.
    class DummyEmbeddings:
        def embed_documents(self, texts):
            return [embeddings_np[0]] * len(texts)
        def embed_query(self, text):
            return embeddings_np[0]
            
    docstore = InMemoryDocstore({})
    index_to_docstore_id = {}
    
    vectorstore = FAISS(
        embedding_function=DummyEmbeddings(),
        index=index,
        docstore=docstore,
        index_to_docstore_id=index_to_docstore_id
    )

    # Add items to FAISS manually with pre-computed embeddings
    ids = []
    for i, mof_id in enumerate(mof_ids):
        doc = Document(
            page_content=f"MOF ID: {mof_id}", 
            metadata={
                "MOF_ID": mof_id,
                "Surface_Area": df.iloc[i]['Surface_Area'],
                "Density": df.iloc[i]['Density'],
                "Pore_Volume": df.iloc[i]['Pore_Volume'],
                "Void_Fraction": df.iloc[i]['Void_Fraction']
            }
        )
        doc_id = str(i)
        vectorstore.docstore.add({doc_id: doc})
        vectorstore.index_to_docstore_id[i] = doc_id
        
    vectorstore.index.add(embeddings_np)
    
    # Save the vector store
    vectorstore.save_local("faiss_ft_index")
    print("Saved FAISS FT-Transformer Index to 'faiss_ft_index'.")
    
    # Save scaler parameters for inference
    pd.DataFrame({'mean': scaler.mean_, 'scale': scaler.scale_}).to_csv('scaler_params.csv', index=False)
    print("Saved scaler parameters.")

if __name__ == "__main__":
    train_and_index()

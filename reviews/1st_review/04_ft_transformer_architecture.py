"""
04_ft_transformer_architecture.py

This file contains the custom PyTorch implementation of the Feature Tokenizer Transformer 
(FT-Transformer), designed to map tabular MOF data into dense vector embeddings for rapid retrieval.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import math

class NumericalFeatureTokenizer(nn.Module):
    """
    Tokenizes continuous numerical features into dense embeddings.
    Standard language models tokenize words; this tokenizes physical properties (e.g. Density).
    """
    def __init__(self, num_features, d_token):
        super().__init__()
        self.num_features = num_features
        self.d_token = d_token
        
        # Learnable weights and biases for each continuous feature
        self.weight = nn.Parameter(torch.Tensor(num_features, d_token))
        self.bias = nn.Parameter(torch.Tensor(num_features, d_token))
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
        nn.init.zeros_(self.bias)

    def forward(self, x):
        # x shape: (batch_size, num_features)
        x = x.unsqueeze(-1) 
        # Returns shape: (batch_size, num_features, d_token)
        return x * self.weight.unsqueeze(0) + self.bias.unsqueeze(0)

class FTTransformer(nn.Module):
    """
    The core Deep Learning model.
    Applies Multi-Head Self-Attention across tabular features to understand the 
    complex physical relationships between Surface Area, Density, Pore Volume, etc.
    """
    def __init__(self, num_features=4, d_token=192, num_heads=4, num_layers=2, output_dim=384):
        super().__init__()
        
        # 1. Tokenizer
        self.tokenizer = NumericalFeatureTokenizer(num_features, d_token)
        
        # 2. CLS Token (Pre-pended to learn the global representation of the MOF)
        self.cls_token = nn.Parameter(torch.randn(1, 1, d_token))
        
        # 3. Multi-Head Attention Transformer Encoder
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_token, nhead=num_heads, dim_feedforward=d_token*2, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # 4. Output projection head (maps to 384-dimensions to align with Sentence-BERT Text Vectors)
        self.head = nn.Linear(d_token, output_dim)

    def forward(self, x):
        batch_size = x.size(0)
        
        # Tokenize tabular features
        tokens = self.tokenizer(x) 
        
        # Attach CLS token
        cls_tokens = self.cls_token.expand(batch_size, -1, -1) 
        x = torch.cat((cls_tokens, tokens), dim=1) 
        
        # Pass through Self-Attention layers
        x = self.transformer(x)
        
        # Extract the global CLS token representation
        cls_repr = x[:, 0, :]
        
        # Project and normalize for Cosine Similarity search in FAISS
        out = self.head(cls_repr)
        return F.normalize(out, p=2, dim=1)

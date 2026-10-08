import torch
import torch.nn as nn
import torch.nn.functional as F

import math

class NumericalFeatureTokenizer(nn.Module):
    """Tokenizes continuous numerical features into dense embeddings."""
    def __init__(self, num_features, d_token):
        super().__init__()
        self.num_features = num_features
        self.d_token = d_token
        # Learnable weights and biases for each feature
        self.weight = nn.Parameter(torch.Tensor(num_features, d_token))
        self.bias = nn.Parameter(torch.Tensor(num_features, d_token))
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
        nn.init.zeros_(self.bias)

    def forward(self, x):
        # x shape: (batch_size, num_features)
        # Returns: (batch_size, num_features, d_token)
        x = x.unsqueeze(-1) # (batch, num_features, 1)
        return x * self.weight.unsqueeze(0) + self.bias.unsqueeze(0)

class FTTransformer(nn.Module):
    """
    Feature Tokenizer + Transformer for Tabular Data.
    Maps tabular features (Surface Area, Density, etc.) to a dense vector space.
    """
    def __init__(self, num_features=4, d_token=192, num_heads=4, num_layers=2, output_dim=384):
        super().__init__()
        # Tokenizer
        self.tokenizer = NumericalFeatureTokenizer(num_features, d_token)
        
        # CLS Token (prepended to learn global representation)
        self.cls_token = nn.Parameter(torch.randn(1, 1, d_token))
        
        # Transformer Encoder
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_token, nhead=num_heads, dim_feedforward=d_token*2, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Output projection to match text embedding dimension (384 for MiniLM)
        self.head = nn.Linear(d_token, output_dim)

    def forward(self, x):
        # x shape: (batch_size, num_features)
        batch_size = x.size(0)
        
        # Tokenize features
        tokens = self.tokenizer(x) # (batch, num_features, d_token)
        
        # Prepend CLS token
        cls_tokens = self.cls_token.expand(batch_size, -1, -1) # (batch, 1, d_token)
        x = torch.cat((cls_tokens, tokens), dim=1) # (batch, num_features+1, d_token)
        
        # Pass through Transformer
        x = self.transformer(x)
        
        # Extract CLS token representation
        cls_repr = x[:, 0, :]
        
        # Project to final output dimension
        out = self.head(cls_repr)
        return F.normalize(out, p=2, dim=1) # L2 normalize for cosine similarity

class FTAutoencoder(nn.Module):
    """
    Self-supervised Autoencoder to pre-train the FT-Transformer without labels.
    Reconstructs the original tabular features from the embedding.
    """
    def __init__(self, encoder):
        super().__init__()
        self.encoder = encoder
        self.decoder = nn.Sequential(
            nn.Linear(384, 192),
            nn.ReLU(),
            nn.Linear(192, 4) # Reconstruct 4 features
        )
        
    def forward(self, x):
        embedding = self.encoder(x)
        reconstruction = self.decoder(embedding)
        return embedding, reconstruction

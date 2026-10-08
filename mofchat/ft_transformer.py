"""
FT-Transformer (Feature Tokenizer + Transformer) for tabular MOF descriptors.

Reference: Gorishniy, Rubachev, Khrulkov & Babenko, "Revisiting Deep Learning
Models for Tabular Data", NeurIPS 2021.

  * FeatureTokenizer  - every numeric feature x_j becomes a token  x_j * W_j + b_j,
                        every categorical feature becomes a learned embedding.
  * [CLS] token       - prepended; its final state summarises the whole MOF.
  * Pre-norm blocks   - multi-head self-attention + feed-forward; attention maps
                        can be returned for explanation (which descriptors the CLS
                        token attends to).

Two heads are built on the same backbone:
  * FTRegressor          - supervised property prediction (e.g. surface area).
  * FTMaskedAutoencoder  - self-supervised: random descriptors are replaced by a
                           [MASK] token and the CLS state must reconstruct all of
                           them. The CLS state is the MOF embedding used for
                           "find MOFs similar to X".
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


class FeatureTokenizer(nn.Module):
    def __init__(self, n_num: int, cat_cardinalities: tuple[int, ...], d_token: int):
        super().__init__()
        self.n_num = n_num
        self.weight = nn.Parameter(torch.empty(n_num, d_token))
        self.bias = nn.Parameter(torch.empty(n_num, d_token))
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
        nn.init.uniform_(self.bias, -1 / math.sqrt(d_token), 1 / math.sqrt(d_token))
        self.cat_embeddings = nn.ModuleList(nn.Embedding(c, d_token) for c in cat_cardinalities)

    def forward(self, x_num: torch.Tensor, x_cat: torch.Tensor | None = None) -> torch.Tensor:
        tokens = x_num.unsqueeze(-1) * self.weight + self.bias           # (B, n_num, d)
        if x_cat is not None and len(self.cat_embeddings):
            cats = [emb(x_cat[:, i]) for i, emb in enumerate(self.cat_embeddings)]
            tokens = torch.cat([tokens, torch.stack(cats, dim=1)], dim=1)
        return tokens


class TransformerBlock(nn.Module):
    def __init__(self, d: int, n_heads: int, ffn_mult: float, dropout: float):
        super().__init__()
        self.norm1 = nn.LayerNorm(d)
        self.attn = nn.MultiheadAttention(d, n_heads, dropout=dropout, batch_first=True)
        self.norm2 = nn.LayerNorm(d)
        hidden = int(d * ffn_mult)
        self.ffn = nn.Sequential(nn.Linear(d, hidden), nn.GELU(), nn.Dropout(dropout), nn.Linear(hidden, d))
        self.drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor, need_weights: bool = False):
        h = self.norm1(x)
        a, w = self.attn(h, h, h, need_weights=need_weights, average_attn_weights=True)
        x = x + self.drop(a)
        x = x + self.drop(self.ffn(self.norm2(x)))
        return x, w


class FTTransformer(nn.Module):
    """Backbone: returns the final [CLS] representation (B, d_token)."""

    def __init__(self, n_num: int, cat_cardinalities: tuple[int, ...] = (), d_token: int = 64,
                 n_layers: int = 3, n_heads: int = 4, ffn_mult: float = 2.0, dropout: float = 0.1):
        super().__init__()
        self.config = dict(n_num=n_num, cat_cardinalities=tuple(cat_cardinalities), d_token=d_token,
                           n_layers=n_layers, n_heads=n_heads, ffn_mult=ffn_mult, dropout=dropout)
        self.tokenizer = FeatureTokenizer(n_num, tuple(cat_cardinalities), d_token)
        self.cls = nn.Parameter(torch.zeros(1, 1, d_token))
        nn.init.normal_(self.cls, std=0.02)
        self.mask_token = nn.Parameter(torch.zeros(1, 1, d_token))   # used by the masked autoencoder
        self.blocks = nn.ModuleList(TransformerBlock(d_token, n_heads, ffn_mult, dropout) for _ in range(n_layers))
        self.norm = nn.LayerNorm(d_token)

    def forward(self, x_num, x_cat=None, num_mask: torch.Tensor | None = None, return_attention: bool = False):
        tokens = self.tokenizer(x_num, x_cat)
        if num_mask is not None:                                       # (B, n_num) bool
            n = num_mask.shape[1]
            masked = torch.where(num_mask.unsqueeze(-1), self.mask_token.expand_as(tokens[:, :n]), tokens[:, :n])
            tokens = torch.cat([masked, tokens[:, n:]], dim=1)
        x = torch.cat([self.cls.expand(len(tokens), -1, -1), tokens], dim=1)
        attentions = []
        for blk in self.blocks:
            x, w = blk(x, need_weights=return_attention)
            if return_attention:
                attentions.append(w)
        cls = self.norm(x[:, 0])
        return (cls, attentions) if return_attention else cls


class FTRegressor(nn.Module):
    def __init__(self, backbone: FTTransformer):
        super().__init__()
        self.backbone = backbone
        d = backbone.config["d_token"]
        self.head = nn.Sequential(nn.ReLU(), nn.Linear(d, 1))

    def forward(self, x_num, x_cat=None):
        return self.head(self.backbone(x_num, x_cat)).squeeze(-1)

    @torch.no_grad()
    def cls_attention(self, x_num, x_cat=None) -> torch.Tensor:
        """Attention from [CLS] to each feature token in the last layer, (B, n_tokens)."""
        _, att = self.backbone(x_num, x_cat, return_attention=True)
        return att[-1][:, 0, 1:]


class FTMaskedAutoencoder(nn.Module):
    def __init__(self, backbone: FTTransformer, mask_prob: float = 0.3):
        super().__init__()
        self.backbone = backbone
        self.mask_prob = mask_prob
        d, n = backbone.config["d_token"], backbone.config["n_num"]
        self.decoder = nn.Sequential(nn.Linear(d, 2 * d), nn.GELU(), nn.Linear(2 * d, n))

    def forward(self, x_num, x_cat=None, mask: torch.Tensor | None = None):
        if mask is None and self.training:
            mask = torch.rand_like(x_num) < self.mask_prob
        cls = self.backbone(x_num, x_cat, num_mask=mask)
        return cls, self.decoder(cls), mask

    @torch.no_grad()
    def embed(self, x_num, x_cat=None) -> torch.Tensor:
        self.eval()
        return F.normalize(self.backbone(x_num, x_cat), dim=1)

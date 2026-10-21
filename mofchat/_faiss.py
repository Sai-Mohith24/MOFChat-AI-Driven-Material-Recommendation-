"""
Safe import order and threading for the native libraries.

On macOS, XGBoost, PyTorch, faiss-cpu (and scikit-learn) each ship their own
copy of the OpenMP runtime (libomp). With several runtimes in one process:
  * some import orders segfault (tested stable order: xgboost -> torch -> faiss);
  * two runtimes with active thread pools can deadlock at an OpenMP barrier
    (observed: torch tensor copy hanging after an XGBoost fit);
  * multi-threaded PyTorch can segfault even without XGBoost (observed with
    torch 2.13: the first numpy -> tensor copy in train_ft.py at 8 threads).
MOFChat therefore runs OpenMP single-threaded by default (OMP_NUM_THREADS=1).
The models are small, so the cost is a few seconds of training time.
MOFCHAT_THREADS=<n> gives PyTorch more threads; use it only where it has been
tested not to crash. Every entry point imports this module first, via
`import mofchat`.
"""

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

try:
    import xgboost  # noqa: F401  (must be loaded before torch)
except ImportError:  # property models are optional at runtime
    pass
import torch  # noqa: E402  (must be loaded before faiss)
import faiss  # noqa: E402

faiss.omp_set_num_threads(1)
torch.set_num_threads(int(os.environ.get("MOFCHAT_THREADS", "1")))

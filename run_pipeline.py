"""
run_pipeline.py - build everything from the raw spreadsheet, in order.

  python run_pipeline.py            # ETL, knowledge index, embeddings, property models, tests
  python run_pipeline.py --eval     # ... and the full six-model evaluation (1.5-2 h, mostly free-tier waits)
"""

import subprocess
import sys

STEPS = [
    ("Build SQLite database", ["setup_db.py"]),
    ("Build knowledge (RAG) index", ["setup_vectorstore.py"]),
    ("Train FT-Transformer embeddings", ["train_ft.py"]),
    ("Train property models (+SHAP)", ["train_property_models.py"]),
    ("Unit tests", ["-m", "pytest", "-q"]),
]

if __name__ == "__main__":
    steps = STEPS + ([("Evaluation", ["evaluate.py"])] if "--eval" in sys.argv else [])
    for name, args in steps:
        print(f"\n=== {name} ===", flush=True)
        if subprocess.run([sys.executable, *args]).returncode != 0:
            sys.exit(f"step failed: {name}")
    print("\nDone. Start the app with:  streamlit run app.py")

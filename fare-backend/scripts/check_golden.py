"""Check that the backend reproduces your NOTEBOOK's predictions.

This is the proof that project/transformer.py behaves like your original one.

1) In your notebook, run:
       import numpy as np
       rows = x_test.head(20)
       rows.to_pickle("golden_rows.pkl")
       np.save("golden_preds.npy", final_pipeline.predict(rows))
2) Copy golden_rows.pkl and golden_preds.npy into this backend's root folder.
3) Run:  python -m scripts.check_golden
"""
import sys

import numpy as np
import pandas as pd

from app.config import get_settings
from app.model_loader import load_pipeline


def main() -> int:
    pipe = load_pipeline(get_settings().resolved_model_path)
    rows = pd.read_pickle("golden_rows.pkl")
    expected = np.load("golden_preds.npy")
    got = pipe.predict(rows)
    diff = float(np.max(np.abs(got - expected)))
    print(f"rows checked: {len(rows)} | max abs difference: {diff:.8f}")
    if np.allclose(got, expected, atol=1e-4):
        print("OK - the backend reproduces the notebook predictions.")
        return 0
    print("MISMATCH - project/transformer.py differs from your original. "
          "Copy your original transformer file over it and run this again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

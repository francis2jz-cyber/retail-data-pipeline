import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BATCH = "test_batch"


@pytest.fixture
def batch_id():
    return BATCH


def frame(rows: list[dict]) -> pd.DataFrame:
    """Build a raw-style DataFrame (all text) from a list of dicts."""
    return pd.DataFrame(rows).astype(str)

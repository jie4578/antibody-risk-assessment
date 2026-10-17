import pandas as pd

from validation.frozen_baseline import assert_frozen_rule_compatibility
from validation.features.extract_rule_features import extract_features


def test_rule_v1_and_scoring_remain_compatible_with_frozen_commit():
    assert_frozen_rule_compatibility()


def test_historical_rule48_extraction_still_uses_v1():
    result = extract_features(pd.DataFrame([{"antibody_id": "synthetic", "VH": "NNST", "VL": "ACD"}]))
    sites = result.risk_sites
    assert len(sites.loc[sites["category"] == "N-糖基化"]) == 1

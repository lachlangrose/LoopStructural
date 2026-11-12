import numpy as np
import pytest

from fault_mmg.geometry import HORIZONS, fault, horizon_height, labels, stratigraphy


def test_fault_has_two_distinct_stratigraphic_traces():
    p = np.array([[0.0, 0.2, 0.7]])
    assert fault(p)[0] == 0
    assert stratigraphy(p, 1)[0] - stratigraphy(p, 2)[0] == pytest.approx(0.4)


def test_all_offset_horizon_planes():
    for block in (1, 2):
        for h in HORIZONS:
            p = np.array([[(-0.5 if block == 1 else 0.5), 0, horizon_height(block, h)]])
            assert stratigraphy(p, block)[0] == pytest.approx(h)
            below = p.copy()
            below[:, 2] -= 1e-5
            above = p.copy()
            above[:, 2] += 1e-5
            assert labels(above)[1][0] == labels(below)[1][0] + 1


def test_block_must_be_explicit_and_valid():
    with pytest.raises(ValueError):
        stratigraphy(np.zeros((1, 3)), 0)

import uuid
from datetime import datetime

import numpy as np
from pydantic import TypeAdapter

from loop_common.base import LoopEntity, NumpyArray


def test_uid_and_mark_modified():
    e = LoopEntity(name="test")
    # uid should be a valid UUID string
    uuid.UUID(e.uid)
    assert e.name == "test"

    old_ts = datetime.fromisoformat(e.last_modified)
    e.mark_modified()
    new_ts = datetime.fromisoformat(e.last_modified)
    assert new_ts > old_ts


def test_json_roundtrip():
    e = LoopEntity(name="roundtrip")
    j = e.to_json()
    e2 = LoopEntity.from_json(j)
    assert e2.uid == e.uid
    assert e2.name == e.name
    assert e2.last_modified == e.last_modified


def test_numpyarray_typeadapter_validate_and_dump():
    ta = TypeAdapter(NumpyArray)
    arr = ta.validate_python([1, 2, 3])
    assert isinstance(arr, np.ndarray)
    dumped = ta.dump_python(arr)
    assert dumped == [1, 2, 3]

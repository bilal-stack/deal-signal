from __future__ import annotations

import pytest

from dealsignal.repositories.base import BaseRepository


def test_a_repository_must_declare_its_model() -> None:
    with pytest.raises(TypeError, match="must set a `model` attribute"):

        class BrokenRepository(BaseRepository):  # type: ignore[type-arg]
            pass

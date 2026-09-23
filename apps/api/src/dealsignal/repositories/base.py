"""Generic repository.

Every table repeats the same four operations. They live here once, typed by model,
so a concrete repository only holds the queries that are actually specific to it.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.errors import NotFoundError
from dealsignal.db.base import Base


class BaseRepository[ModelT: Base]:
    """CRUD shared by every repository.

    Subclass it and set `model`:

        class CompanyRepository(BaseRepository[Company]):
            model = Company
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "model"):
            raise TypeError(f"{cls.__name__} must set a `model` attribute.")

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def get_or_raise(self, entity_id: uuid.UUID) -> ModelT:
        """Same as `get`, but raises the error the API layer knows how to render."""
        entity = await self.get(entity_id)
        if entity is None:
            raise NotFoundError(f"{self.model.__name__} {entity_id} was not found.")
        return entity

    async def list(self, *, limit: int = 50, offset: int = 0) -> list[ModelT]:
        result = await self.session.scalars(select(self.model).limit(limit).offset(offset))
        return list(result)

    async def count(self) -> int:
        total = await self.session.scalar(select(func.count()).select_from(self.model))
        return int(total or 0)

    def add(self, entity: ModelT) -> ModelT:
        """Stage an insert. The surrounding session commits it."""
        self.session.add(entity)
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)

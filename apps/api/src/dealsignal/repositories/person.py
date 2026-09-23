"""People storage: owners and directors."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from dealsignal.models.person import Person
from dealsignal.repositories.base import BaseRepository


class PersonRepository(BaseRepository[Person]):
    model = Person

    async def for_company(self, company_id: uuid.UUID) -> list[Person]:
        result = await self.session.scalars(select(Person).where(Person.company_id == company_id))
        return list(result)

    async def upsert_by_name(self, person: Person) -> Person:
        """Add a person, or update the one we already hold under that name.

        Re-running a register lookup must not create a second copy of the same
        director, and a later run that learns a birth year must be able to fill it in.
        """
        existing = await self.session.scalar(
            select(Person).where(
                Person.company_id == person.company_id,
                Person.full_name == person.full_name,
            )
        )
        if existing is None:
            self.session.add(person)
            return person

        existing.role = person.role or existing.role
        existing.birth_year = person.birth_year or existing.birth_year
        existing.appointed_year = person.appointed_year or existing.appointed_year
        existing.is_owner = existing.is_owner or person.is_owner
        return existing

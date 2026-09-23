"""Exported rows: the score travels with its reasons, and unknown stays empty."""

from __future__ import annotations

import csv
import io

from dealsignal.models.company import Company
from dealsignal.models.enums import Country, SourceName
from dealsignal.models.person import Person
from dealsignal.scoring.base import SignalResult
from dealsignal.scoring.scorer import ScoreResult
from dealsignal.services.export import COLUMNS, build_row, filename_for, to_csv


def company(**overrides: object) -> Company:
    defaults: dict[str, object] = {
        "display_name": "Arma Plomberie",
        "normalized_name": "arma plomberie",
        "country": Country.FR,
        "city": "Lyon",
        "founded_year": 2001,
    }
    return Company(**{**defaults, **overrides})


def result(score: float | None = 92.5) -> ScoreResult:
    return ScoreResult(
        score=score,
        confidence=0.45,
        reasons=[
            SignalResult(
                key="years_in_business",
                points=15,
                max_points=15,
                reason="Founded 2001 (25 years in business)",
            ),
            SignalResult(
                key="owner_age",
                points=15,
                max_points=15,
                reason="Owner born 1964, around 62 years old",
            ),
        ],
        missing_signals=["revenue_fit", "employee_fit"],
    )


def test_a_row_carries_the_score_and_the_reasons() -> None:
    row = build_row(company(), result(), sources=["overture", "recherche_entreprises"])

    assert row["Company"] == "Arma Plomberie"
    assert row["Score"] == 92.5
    assert row["Confidence"] == "medium"
    assert "Founded 2001" in row["Why (top reasons)"]
    assert "Owner born 1964" in row["Why (top reasons)"]
    assert row["Unknown signals"] == 2
    assert row["Sources"] == "overture, recherche_entreprises"


def test_an_unscorable_company_leaves_the_score_cell_empty() -> None:
    """Empty, not zero: a spreadsheet sorted by score must not rank guesses."""
    row = build_row(company(), result(score=None))

    assert row["Score"] == ""


def test_unknown_fields_are_empty_not_placeholders() -> None:
    row = build_row(company(phone_e164=None, revenue_low=None), None)

    assert row["Phone"] == ""
    assert row["Revenue low (est.)"] == ""
    assert row["Owner"] == ""
    assert "N/A" not in str(row.values())


def test_the_owner_with_a_birth_year_is_the_one_exported() -> None:
    people = [
        Person(full_name="Sans Date", is_owner=True, source=SourceName.RECHERCHE_ENTREPRISES),
        Person(
            full_name="Marie Durand",
            is_owner=True,
            birth_year=1964,
            source=SourceName.RECHERCHE_ENTREPRISES,
        ),
    ]

    row = build_row(company(), result(), people=people)

    assert row["Owner"] == "Marie Durand"
    assert row["Owner born"] == 1964


def test_csv_round_trips_with_the_expected_headers() -> None:
    body = to_csv([build_row(company(), result())])
    text = body.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))

    assert list(rows[0].keys()) == list(COLUMNS)
    assert rows[0]["Company"] == "Arma Plomberie"


def test_csv_starts_with_a_bom_so_excel_reads_accents() -> None:
    assert to_csv([build_row(company(), result())]).startswith(b"\xef\xbb\xbf")


def test_the_filename_says_what_and_when() -> None:
    name = filename_for("HVAC, Dallas", "xlsx")

    assert name.startswith("dealsignal-HVAC--Dallas-")
    assert name.endswith(".xlsx")

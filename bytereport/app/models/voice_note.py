"""
Free-form note -> structured draft transactions.

A DRAFT is not a Transaction. `app.models.transaction.Transaction` is what the
analysis pipeline consumes and every field on it is required and validated; a
draft is what the model produced from a spoken sentence, where the date may be
missing, the amount may have been misheard and the category may be a guess.
Keeping them as separate types is what makes the preview step enforceable: no
draft can reach the pipeline without a human turning it into a Transaction.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Direction = Literal["income", "expense"]

# Fields the model is allowed to flag. A closed set, because the frontend
# renders a hint per field name and an invented name would render nowhere.
DraftField = Literal["date", "amount", "direction", "description", "category"]

# Where a row's date came from. "stated" = printed or spoken outright,
# "relative" = resolved from words like "вчера", "assumed" = the model had
# nothing to go on. See _flag_assumed_today for why this is asked for.
DateSource = Literal["stated", "relative", "assumed"]

# Below this many records a single note cannot support trend analysis, a Health
# Score or a forecast. Named here rather than inlined so the accumulation phase
# has one number to move.
MIN_RECORDS_FOR_ANALYSIS = 30


class DraftTransaction(BaseModel):
    """One movement of money as the model understood it."""

    # ISO date, or None when the note never said. Not a `date` type: an unparsed
    # fragment ("прошлая среда") must survive to the preview so the user can see
    # what was heard and correct it, rather than being silently dropped.
    date: Optional[str] = None
    # Evidence for the date, not decoration: the guard in voice_parser only
    # trusts a date equal to today when the model claims it read one.
    date_source: Optional[DateSource] = None
    amount: Optional[float] = None
    direction: Direction
    description: str = ""
    category: Optional[str] = None
    # Currency the AMOUNT is expressed in. The model fills this from the note's
    # own words ("двести долларов"); after conversion it holds the business
    # currency, and notes["amount"] cites the rate that got it there.
    currency: Optional[str] = None

    # Per-FIELD uncertainty, not per-record: a note usually gets the amount
    # right and the date wrong, and flagging the whole row would hide that.
    uncertain: list[DraftField] = Field(default_factory=list)
    # field name -> short human reason, shown inline next to that cell.
    notes: dict[str, str] = Field(default_factory=dict)

    @field_validator("amount")
    @classmethod
    def amount_not_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        # Direction carries the sign; a negative amount would double-count it.
        return round(abs(v), 2)

    @field_validator("uncertain")
    @classmethod
    def dedupe(cls, v: list[str]) -> list[str]:
        seen: list[str] = []
        for item in v:
            if item not in seen:
                seen.append(item)
        return seen


class TranscriptionResponse(BaseModel):
    text: str
    # What the speech model detected, which need not be the UI language.
    detected_language: Optional[str] = None
    duration_seconds: Optional[float] = None


class ParseNoteRequest(BaseModel):
    text: str
    language: str = "ru"
    currency: str = "UZS"


class ParseNoteResponse(BaseModel):
    transactions: list[DraftTransaction]
    warnings: list[str] = Field(default_factory=list)
    # Echoed back so the preview can sit beside exactly the text that produced
    # it, even if the user has since edited the textarea.
    source_text: str = ""

    # Seam for the accumulation phase. Today this is always False with the same
    # reason; when notes start being stored, the same field flips to True once
    # enough records exist and the frontend needs no change.
    analysis_available: bool = False
    records_needed: int = MIN_RECORDS_FOR_ANALYSIS


class ExcelRequest(BaseModel):
    """
    The CONFIRMED draft. There is deliberately no endpoint that goes from raw
    text to a file: the only way to reach a workbook is to post rows a human
    has seen.
    """

    transactions: list[DraftTransaction]
    business_name: Optional[str] = None
    currency: str = "UZS"
    language: str = "ru"

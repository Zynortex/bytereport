from pydantic import BaseModel, field_validator
from datetime import date
from typing import Optional
from enum import Enum


class TransactionType(str, Enum):
    income = "income"
    expense = "expense"


class Transaction(BaseModel):
    date: date
    description: str
    amount: float
    type: TransactionType
    category: str
    raw_category: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("amount must be positive")
        return round(v, 2)


class ParseResult(BaseModel):
    transactions: list[Transaction]
    total_rows: int
    skipped_rows: int
    warnings: list[str]

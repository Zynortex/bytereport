import pytest
from app.services.csv_parser import parse_csv
from app.models.transaction import TransactionType


SAMPLE_EN = """date,amount,type,category,description
2024-01-15,5000.00,income,sales,Product sale
2024-01-16,1200.50,expense,marketing,Google Ads
2024-01-17,300.00,expense,software,SaaS subscription
2024-01-18,8000.00,income,services,Consulting project
"""

SAMPLE_RU = """дата;сумма;тип;категория;описание
15.01.2024;5000,00;доход;продажи;Продажа товара
16.01.2024;1200,50;расход;реклама;Google Ads
17.01.2024;300,00;расход;подписка;SaaS подписка
18.01.2024;8000,00;доход;услуги;Консультация
"""

SAMPLE_SIGNED = """date,amount,description
2024-01-15,5000.00,Product sale
2024-01-16,-1200.50,Google Ads
2024-01-17,-300.00,SaaS subscription
"""

SAMPLE_MISSING_AMOUNT = """date,amount,type,description
2024-01-15,,income,Empty amount row
2024-01-16,500.00,expense,Valid row
"""


def test_parse_english_csv():
    result = parse_csv(SAMPLE_EN)
    assert result.total_rows == 4
    assert result.skipped_rows == 0
    assert len(result.transactions) == 4
    assert result.transactions[0].type == TransactionType.income
    assert result.transactions[0].amount == 5000.00
    assert result.transactions[1].type == TransactionType.expense


def test_parse_russian_csv_semicolon():
    result = parse_csv(SAMPLE_RU.encode("utf-8"))
    assert result.total_rows == 4
    assert len(result.transactions) == 4
    assert result.transactions[0].type == TransactionType.income
    assert result.transactions[0].amount == 5000.00


def test_infer_type_from_signed_amount():
    result = parse_csv(SAMPLE_SIGNED)
    assert result.transactions[0].type == TransactionType.income
    assert result.transactions[1].type == TransactionType.expense
    assert result.transactions[1].amount == 1200.50


def test_skips_empty_required_fields():
    result = parse_csv(SAMPLE_MISSING_AMOUNT)
    assert result.skipped_rows == 1
    assert len(result.transactions) == 1
    assert len(result.warnings) >= 1


def test_empty_content_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_csv(b"")


def test_missing_required_column_raises():
    bad_csv = "description,type\nsome desc,income\n"
    with pytest.raises(ValueError, match="Required columns not found"):
        parse_csv(bad_csv)


def test_category_normalization():
    csv_data = "date,amount,type,category,description\n2024-01-15,500,expense,реклама Google,таргет кампания\n"
    result = parse_csv(csv_data)
    assert result.transactions[0].category == "marketing"

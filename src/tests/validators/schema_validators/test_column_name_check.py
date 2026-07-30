import polars as pl

from argus.loaders.base_excel_loader import ExcelLoaderData
from argus.loaders.excel_loader import DataSheetMap
from argus.validators.schema_validators.column_name_validator import (
    ColumnNameCheck,
)
from tests.helpers import do_basic_checks


def get_validator(ignore_sheets: list[str] | None = None):
    """Create a UniqueColumn validator instance"""
    return ColumnNameCheck(ignore_sheets=ignore_sheets)


def build_excel_data(columns: list[str]):
    """Create ExcelLoaderData with matching columns"""
    columns_dict: list[dict[str, list[int]]] = []
    for column in columns:
        columns_dict.append({column: [1, 2, 3, 4, 5]})

    df = pl.DataFrame(columns_dict)

    loaded_sheet = DataSheetMap(
        schema_sheet_name="raw_data",
        data_sheet_name="raw_data",
        data=df,
    )

    return ExcelLoaderData(
        loaded_sheets=[loaded_sheet],
    )


class TestColumnNames:
    def test_valid_columns(
        self,
    ):

        data = build_excel_data(["some_column", "some.column", "somecolumn"])
        validator = get_validator()
        result = validator.validate(data)

        do_basic_checks(result, 0)

    def test_invalid_column(
        self,
    ):

        data = build_excel_data(["some@column"])
        validator = get_validator()
        result = validator.validate(data)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert result[0].details["columns"][0] == "some@column"

    def test_invalid_column2(
        self,
    ):

        data = build_excel_data(["some column"])
        validator = get_validator()
        result = validator.validate(data)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert result[0].details["columns"][0] == "some column"

    def test_ignore_sheet(
        self,
    ):

        data = build_excel_data(["some@column"])
        validator = get_validator(ignore_sheets=["raw_data"])
        result = validator.validate(data)

        do_basic_checks(result, 0)

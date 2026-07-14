import polars as pl
import pytest

from argus.loaders.base_excel_loader import ExcelLoaderData
from argus.loaders.excel_loader import DataSheetMap
from argus.models.base import SchemaColumnMap, SchemaSheetMap
from argus.models.base_dataset_schemas import BaseDatasetSchema
from argus.validators.base import BaseValidator
from argus.validators.schema_validators.duplicate_sheet_match_validator import (
    DuplicateSheetMatchCheck,
)
from tests.helpers import do_basic_checks


@pytest.fixture
def valid_schema_validator(valid_schema):
    """Create a UniqueColumn validator instance"""
    return DuplicateSheetMatchCheck(valid_schema)


@pytest.fixture
def valid_schema():

    return BaseDatasetSchema(
        dataset_type="jmmi",
        schema_loaded_sheets=[
            SchemaSheetMap(
                standard_name="raw_data",
                alternate_names=["raw_data"],
                mandatory_columns=[
                    SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"])
                ],
            )
        ],
        schema_unloaded_sheets=[],
    )


@pytest.fixture
def valid_excel_data():
    """Create ExcelLoaderData with matching columns"""
    df = pl.DataFrame(
        {
            "uuid": [1, 2, 3, 4, 5],
        }
    )

    loaded_sheet = DataSheetMap(
        schema_sheet_name="raw_data",
        data_sheet_name="raw_data",
        data=df,
    )

    return ExcelLoaderData(loaded_sheets=[loaded_sheet])


@pytest.fixture
def invalid_excel_data():
    """Create ExcelLoaderData with matching columns"""
    df = pl.DataFrame(
        {
            "uuid": [1, 2, 3, 4, 5],
        }
    )
    df2 = pl.DataFrame(
        {
            "uuid": [1, 2, 3, 4, 5],
        }
    )

    loaded_sheets = [
        DataSheetMap(
            schema_sheet_name="raw_data",
            data_sheet_name="raw_data",
            data=df,
        ),
        DataSheetMap(
            schema_sheet_name="raw_data",
            data_sheet_name="raw_data2",
            data=df2,
        ),
    ]

    return ExcelLoaderData(loaded_sheets=loaded_sheets)


class TestMissingSheets:
    def test_valid_schema(
        self, valid_schema_validator: BaseValidator, valid_excel_data: ExcelLoaderData
    ):
        result = valid_schema_validator.validate(valid_excel_data)

        do_basic_checks(result, 0)

    def test_invalid_data(
        self, valid_schema_validator: BaseValidator, invalid_excel_data: ExcelLoaderData
    ):
        result = valid_schema_validator.validate(invalid_excel_data)

        do_basic_checks(result, 1)

import polars as pl

from argus.loaders.base import (
    DataColumnMap,
    DataSheetMap,
)
from argus.loaders.base_excel_loader import ExcelLoaderData
from argus.models.base import SchemaColumnMap, SchemaSheetMap
from argus.models.base_dataset_schemas import BaseDatasetSchema
from argus.validators.schema_validators.mandatory_column_validator import (
    MandatoryColumnsCheck,
)
from tests.helpers import do_basic_checks


def get_validator(schema):
    """Create a UniqueColumn validator instance"""
    return MandatoryColumnsCheck(schema=schema)


def build_schema(sheet_name: str, columns: list[tuple[str, bool]], required=True):
    column_map: list[SchemaColumnMap] = []
    for column in columns:
        column_map.append(SchemaColumnMap(standard_name=column[0], required=column[1]))

    return BaseDatasetSchema(
        dataset_type="jmmi",
        schema_loaded_sheets=[
            SchemaSheetMap(standard_name=sheet_name, columns=column_map, required=required)
        ],
        schema_unloaded_sheets=[],
    )


def build_excel_data(sheet_name: str, columns: list[str]):
    """Create ExcelLoaderData with matching columns"""
    column_map: list[DataColumnMap] = []
    df = pl.DataFrame(
        {
            "uuid": [1, 2, 3, 4, 5],
        }
    )
    for column in columns:
        column_map.append(DataColumnMap(schema_column_name=column, data_column_name=column))

    loaded_sheet = DataSheetMap(
        schema_sheet_name=sheet_name,
        data_sheet_name=sheet_name,
        data=df,
        column_map=column_map,
    )

    return ExcelLoaderData(loaded_sheets=[loaded_sheet])


class TestMandatoryColumns:
    def test_valid_schema(
        self,
    ):
        schema = build_schema("clean_data", [("uuid", True), ("country", True)])
        data = build_excel_data("clean_data", ["uuid", "country"])
        validator = get_validator(schema)

        result = validator.validate(data)

        do_basic_checks(result, 0)

    def test_no_mandatory_columns(
        self,
    ):
        schema = build_schema("clean_data", [("uuid", False), ("country", False)])
        data = build_excel_data("clean_data", ["uuid", "country"])
        validator = get_validator(schema)

        result = validator.validate(data)

        do_basic_checks(result, 0)

    def test_missing_required_column(
        self,
    ):
        schema = build_schema("clean_data", [("uuid", True), ("country", True)])
        data = build_excel_data("clean_data", ["uuid"])
        validator = get_validator(schema)

        result = validator.validate(data)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["required"]) == 1
        assert result[0].details["required"][0] == "Yes"

    def test_multiple_missing_required_column(
        self,
    ):
        schema = build_schema("clean_data", [("uuid", True), ("country", True), ("admin_1", True)])
        data = build_excel_data("clean_data", ["uuid"])
        validator = get_validator(schema)

        result = validator.validate(data)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["required"]) == 2
        assert result[0].details["required"][0] == "Yes"

    def test_missing_required_column_optional_sheet(
        self,
    ):
        schema = build_schema("clean_data", [("uuid", True), ("country", True)], required=False)
        data = build_excel_data("clean_data", ["uuid"])
        validator = get_validator(schema)

        result = validator.validate(data)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["required"]) == 1
        assert result[0].details["required"][0] == "Yes"

    def test_missing_optional_column(
        self,
    ):
        schema = build_schema("clean_data", [("uuid", True), ("country", False)])
        data = build_excel_data("clean_data", ["uuid"])
        validator = get_validator(schema)

        result = validator.validate(data)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["required"]) == 1
        assert result[0].details["required"][0] == "Check if required"

    def test_missing_optional_column_optional_sheet(
        self,
    ):
        schema = build_schema("clean_data", [("uuid", True), ("country", False)], required=False)
        data = build_excel_data("clean_data", ["uuid"])
        validator = get_validator(schema)

        result = validator.validate(data)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["required"]) == 1
        assert result[0].details["required"][0] == "Check if required"

    def test_missing_sheet(
        self,
    ):
        schema = build_schema("clean_data", [("uuid", True), ("country", True)])
        data = build_excel_data("raw_data", ["uuid"])
        validator = get_validator(schema)

        result = validator.validate(data)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["missing_sheets"]) == 1

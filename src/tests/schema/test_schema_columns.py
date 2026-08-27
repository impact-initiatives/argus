import pytest

from argus.models.base import SchemaColumnMap, SchemaSheetMap
from argus.models.base_dataset_schemas import BaseDatasetSchema
from argus.models.preprocess import validate_schema
from tests.helpers import do_basic_checks


@pytest.fixture
def valid_schema():

    return BaseDatasetSchema(
        programme_type="jmmi",
        output_type="dataset",
        schema_loaded_sheets=[
            SchemaSheetMap(
                standard_name="raw_data",
                alternate_names=["raw_data"],
                columns=[SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"])],
            )
        ],
        schema_unloaded_sheets=[],
    )


@pytest.fixture
def invalid_schema_duplicate_columns():

    return BaseDatasetSchema(
        programme_type="jmmi",
        output_type="dataset",
        schema_loaded_sheets=[
            SchemaSheetMap(
                standard_name="raw_data",
                alternate_names=["raw_data"],
                columns=[
                    SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"]),
                    SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"]),
                ],
            )
        ],
        schema_unloaded_sheets=[],
    )


@pytest.fixture
def invalid_schema_duplicate_columns_alt():

    return BaseDatasetSchema(
        programme_type="jmmi",
        output_type="dataset",
        schema_loaded_sheets=[
            SchemaSheetMap(
                standard_name="raw_data",
                alternate_names=["raw_data"],
                columns=[
                    SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"]),
                    SchemaColumnMap(standard_name="other", alternate_names=["uuid"]),
                ],
            )
        ],
        schema_unloaded_sheets=[],
    )


class TestSchemaColumns:
    def test_valid_schema(self, valid_schema: BaseDatasetSchema):
        result = validate_schema(valid_schema)

        do_basic_checks(result, 0)

    def test_duplicate_columns(self, invalid_schema_duplicate_columns: BaseDatasetSchema):
        result = validate_schema(invalid_schema_duplicate_columns)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["columns"]) == 2

    def test_duplicate_columns_alt(self, invalid_schema_duplicate_columns_alt: BaseDatasetSchema):
        result = validate_schema(invalid_schema_duplicate_columns_alt)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert len(result[0].details["columns"]) == 1

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
        schema_unloaded_sheets=[
            SchemaSheetMap(standard_name="read_me", alternate_names=["read_me"])
        ],
    )


@pytest.fixture
def invalid_schema_duplicate_sheets():

    return BaseDatasetSchema(
        programme_type="jmmi",
        output_type="dataset",
        schema_loaded_sheets=[
            SchemaSheetMap(
                standard_name="raw_data",
                alternate_names=["raw_data"],
                columns=[SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"])],
            ),
            SchemaSheetMap(
                standard_name="raw_data",
                alternate_names=["raw_data"],
                columns=[SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"])],
            ),
        ],
        schema_unloaded_sheets=[
            SchemaSheetMap(standard_name="read_me", alternate_names=["read_me"])
        ],
    )


@pytest.fixture
def invalid_schema_duplicate_sheets_alt():

    return BaseDatasetSchema(
        programme_type="jmmi",
        output_type="dataset",
        schema_loaded_sheets=[
            SchemaSheetMap(
                standard_name="raw_data",
                alternate_names=["raw_data"],
                columns=[SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"])],
            ),
            SchemaSheetMap(
                standard_name="clean_data",
                alternate_names=["raw_data"],
                columns=[SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"])],
            ),
        ],
        schema_unloaded_sheets=[],
    )


@pytest.fixture
def invalid_schema_duplicate_unloaded_sheets():

    return BaseDatasetSchema(
        programme_type="jmmi",
        output_type="dataset",
        schema_loaded_sheets=[
            SchemaSheetMap(
                standard_name="raw_data",
                alternate_names=["raw_data"],
                columns=[SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"])],
            ),
        ],
        schema_unloaded_sheets=[
            SchemaSheetMap(standard_name="read_me", alternate_names=["read_me"]),
            SchemaSheetMap(standard_name="analysis", alternate_names=["read_me"]),
        ],
    )


@pytest.fixture
def invalid_schema_duplicate_loaded_unloaded_sheets():

    return BaseDatasetSchema(
        programme_type="jmmi",
        output_type="dataset",
        schema_loaded_sheets=[
            SchemaSheetMap(
                standard_name="raw_data",
                alternate_names=["raw_data"],
                columns=[SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"])],
            ),
        ],
        schema_unloaded_sheets=[
            SchemaSheetMap(standard_name="read_me", alternate_names=["read_me"]),
            SchemaSheetMap(standard_name="raw_data", alternate_names=["raw_data"]),
        ],
    )


@pytest.fixture
def invalid_schema_duplicate_loaded_unloaded_sheets_alt():

    return BaseDatasetSchema(
        programme_type="jmmi",
        output_type="dataset",
        schema_loaded_sheets=[
            SchemaSheetMap(
                standard_name="raw_data",
                alternate_names=["raw_data"],
                columns=[SchemaColumnMap(standard_name="uuid", alternate_names=["uuid", "X_uuid"])],
            ),
        ],
        schema_unloaded_sheets=[
            SchemaSheetMap(standard_name="read_me", alternate_names=["read_me"]),
            SchemaSheetMap(standard_name="analysis", alternate_names=["raw_data"]),
        ],
    )


class TestSchemaSheets:
    def test_valid_schema(self, valid_schema: BaseDatasetSchema):
        result = validate_schema(valid_schema)

        do_basic_checks(result, 0)

    def test_duplicate_sheets(self, invalid_schema_duplicate_sheets: BaseDatasetSchema):
        result = validate_schema(invalid_schema_duplicate_sheets)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert result[0].details["sheets"][0] == "raw_data"

    def test_duplicate_sheets_alt(self, invalid_schema_duplicate_sheets_alt: BaseDatasetSchema):
        result = validate_schema(invalid_schema_duplicate_sheets_alt)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert result[0].details["sheets"][0] == "raw_data"

    def test_duplicate_unloaded_sheets(
        self, invalid_schema_duplicate_unloaded_sheets: BaseDatasetSchema
    ):
        result = validate_schema(invalid_schema_duplicate_unloaded_sheets)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert result[0].details["sheets"][0] == "read_me"

    def test_duplicate_loaded_unloaded_sheets(
        self, invalid_schema_duplicate_loaded_unloaded_sheets: BaseDatasetSchema
    ):
        result = validate_schema(invalid_schema_duplicate_loaded_unloaded_sheets)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert result[0].details["sheets"][0] == "raw_data"

    def test_duplicate_loaded_unloaded_sheets_alt(
        self, invalid_schema_duplicate_loaded_unloaded_sheets_alt: BaseDatasetSchema
    ):
        result = validate_schema(invalid_schema_duplicate_loaded_unloaded_sheets_alt)

        do_basic_checks(result, 1)
        assert result[0].details is not None
        assert result[0].details["sheets"][0] == "raw_data"

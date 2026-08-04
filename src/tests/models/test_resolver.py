from unittest.mock import MagicMock, patch

import pytest

from argus.models.base import SchemaColumnMap, SchemaSheetMap
from argus.models.base_dataset_schemas import BaseDatasetSchema
from src.argus.models.resolver import ResolveDataset
from src.argus.validators.data_validators.nan_check_validator import NaNDataCheck
from src.argus.validators.data_validators.survey_choices_validator import SurveyChoicesCheck


@pytest.fixture
def mock_yaml_loader():
    """Mock fixture for load_file function"""
    with patch("src.argus.models.resolver.load_file") as mock_load:
        # Configure the return value: (raw_data, definitions)
        yield mock_load


def build_schema(sheet_name: str, columns: list[str]):
    column_map: list[SchemaColumnMap] = []
    for column in columns:
        column_map.append(SchemaColumnMap(standard_name=column))

    return BaseDatasetSchema(
        dataset_type="jmmi",
        schema_loaded_sheets=[SchemaSheetMap(standard_name=sheet_name, columns=column_map)],
        schema_unloaded_sheets=[],
    )


class TestDatasetResolver:
    def test_valid_dataset(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.return_value = (
            {
                "dataset_type": "jmmi_dataset",
                "schema_loaded_sheets": [
                    {
                        "standard_name": "clean_data",
                        "alternate_names": ["also_clean"],
                        "allow_fuzzy_matching": False,
                        "columns": [{"standard_name": "uuid"}],
                    }
                ],
                "schema_unloaded_sheets": [{"standard_name": "other_data"}],
            },
            {},
        )
        resolver = ResolveDataset()

        result = resolver.resolve_schema("some/file.yaml")
        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert len(result.schema_loaded_sheets) == 1
        assert result.schema_loaded_sheets[0].standard_name == "clean_data"
        assert result.schema_loaded_sheets[0].alternate_names[0] == "also_clean"
        assert not result.schema_loaded_sheets[0].allow_fuzzy_matching
        assert result.schema_loaded_sheets[0].columns[0].standard_name == "uuid"
        assert result.dataset_type == "jmmi_dataset"
        assert result.schema_unloaded_sheets[0].standard_name == "other_data"

    def test_invalid_dataset(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.return_value = (
            {
                "dataset_type": "jmmi_dataset",
                "schema_loaded_sheets": [
                    {
                        "standard_name_invalid": "clean_data",
                        "alternate_names": ["also_clean"],
                        "allow_fuzzy_matching": False,
                        "columns": [{"standard_name": "uuid"}],
                    }
                ],
                "schema_unloaded_sheets": [{"standard_name": "other_data"}],
            },
            {},
        )
        resolver = ResolveDataset()
        with pytest.raises(ValueError) as e_info:
            _ = resolver.resolve_schema("some/file.yaml")
        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert "Schema validation failed" in str(e_info.value)

    def test_missing_reference(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.return_value = (
            {
                "dataset_type": "jmmi_dataset",
                "schema_loaded_sheets": [{"$use": "clean_data"}],
                "schema_unloaded_sheets": [{"standard_name": "other_data"}],
            },
            {},
        )
        resolver = ResolveDataset()
        with pytest.raises(RuntimeError) as e_info:
            _ = resolver.resolve_schema("some/file.yaml")
        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert "Missing definition" in str(e_info.value)

    def test_import_sheet(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.side_effect = [
            (
                {
                    "dataset_type": "jmmi_dataset",
                    "schema_loaded_sheets": [{"$use": "clean_data_sheet"}],
                    "schema_unloaded_sheets": [],
                },
                {
                    "clean_data_sheet": {"standard_name": "clean_data"},
                },
            ),
        ]

        resolver = ResolveDataset()
        result = resolver.resolve_schema("some/file.yaml")
        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert len(result.schema_loaded_sheets) == 1
        assert result.schema_loaded_sheets[0].standard_name == "clean_data"

    def test_import_sheet_append_columns(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.side_effect = [
            (
                {
                    "dataset_type": "jmmi_dataset",
                    "schema_loaded_sheets": [
                        {
                            "$use": "clean_data_sheet",
                            "$append_columns": [{"standard_name": "country"}],
                        }
                    ],
                    "schema_unloaded_sheets": [],
                },
                {
                    "clean_data_sheet": {"standard_name": "clean_data"},
                },
            ),
        ]

        resolver = ResolveDataset()
        result = resolver.resolve_schema("some/file.yaml")
        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert len(result.schema_loaded_sheets) == 1
        assert result.schema_loaded_sheets[0].standard_name == "clean_data"
        assert result.schema_loaded_sheets[0].columns[0].standard_name == "country"

    def test_import_sheet_append_imported_columns(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.side_effect = [
            (
                {
                    "dataset_type": "jmmi_dataset",
                    "schema_loaded_sheets": [
                        {
                            "$use": "clean_data_sheet",
                            "$append_columns": [{"$use": "uuid_column"}],
                        }
                    ],
                    "schema_unloaded_sheets": [],
                },
                {
                    "clean_data_sheet": {"standard_name": "clean_data"},
                    "uuid_column": {"standard_name": "uuid"},
                },
            ),
        ]

        resolver = ResolveDataset()
        result = resolver.resolve_schema("some/file.yaml")
        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert len(result.schema_loaded_sheets) == 1
        assert result.schema_loaded_sheets[0].standard_name == "clean_data"
        assert result.schema_loaded_sheets[0].columns[0].standard_name == "uuid"

    def test_import_sheet_override(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.side_effect = [
            (
                {
                    "dataset_type": "jmmi_dataset",
                    "schema_loaded_sheets": [
                        {
                            "$use": "clean_data_sheet",
                            "override": {"alternate_names": ["new_name"]},
                        }
                    ],
                    "schema_unloaded_sheets": [],
                },
                {
                    "clean_data_sheet": {
                        "standard_name": "clean_data",
                        "alternate_names": ["original_name"],
                    },
                },
            ),
        ]

        resolver = ResolveDataset()
        result = resolver.resolve_schema("some/file.yaml")
        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert len(result.schema_loaded_sheets) == 1
        assert result.schema_loaded_sheets[0].standard_name == "clean_data"
        assert result.schema_loaded_sheets[0].alternate_names[0] == "new_name"


class TestValidatorResolver:
    def test_valid_validator(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.return_value = ({"validators": [{"type": "NaNDataCheck"}]}, {})
        schema = build_schema("clean_data", ["uuid"])

        resolver = ResolveDataset()
        result = resolver.resolve_validators("some/file.yaml", schema)

        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert len(result) == 1
        assert isinstance(result[0], NaNDataCheck)

    def test_valid_validator_with_paramaters(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.return_value = (
            {
                "validators": [
                    {"type": "SurveyChoicesCheck", "kwargs": {"check_sheets": ["clean_data_here"]}}
                ]
            },
            {},
        )
        schema = build_schema("clean_data", ["uuid"])

        resolver = ResolveDataset()
        result = resolver.resolve_validators("some/file.yaml", schema)

        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert len(result) == 1
        assert result[0].__class__.__name__ == "SurveyChoicesCheck"
        assert isinstance(result[0], SurveyChoicesCheck)
        assert result[0].check_sheets == ["clean_data_here"]

    def test_invalid_validator(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.return_value = ({"validators": [{"type": "FakeValidator"}]}, {})
        schema = build_schema("clean_data", ["uuid"])

        resolver = ResolveDataset()
        with pytest.raises(ValueError) as e_info:
            _ = resolver.resolve_validators("some/file.yaml", schema)

        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert "FakeValidator" in str(e_info.value)
        assert "Unknown validator" in str(e_info.value)

    def test_invalid_yaml_type(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.return_value = ({"validators": [{"typeinvalid": "NaNDataCheck"}]}, {})
        schema = build_schema("clean_data", ["uuid"])

        resolver = ResolveDataset()
        with pytest.raises(ValueError) as e_info:
            _ = resolver.resolve_validators("some/file.yaml", schema)

        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert "missing 'type'" in str(e_info.value)

    def test_invalid_yaml_dict(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.return_value = ({"validators": {"type": "NaNDataCheck"}}, {})
        schema = build_schema("clean_data", ["uuid"])

        resolver = ResolveDataset()
        with pytest.raises(ValueError) as e_info:
            _ = resolver.resolve_validators("some/file.yaml", schema)

        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert "not a dictionary" in str(e_info.value)

    def test_validator_with_invalid_paramaters(self, mock_yaml_loader: MagicMock):
        mock_yaml_loader.return_value = (
            {
                "validators": [
                    {
                        "type": "SurveyChoicesCheck",
                        "kwargs": {"check_sheets_invalid": ["clean_data_here"]},
                    }
                ]
            },
            {},
        )
        schema = build_schema("clean_data", ["uuid"])

        resolver = ResolveDataset()
        with pytest.raises(ValueError) as e_info:
            _ = resolver.resolve_validators("some/file.yaml", schema)

        mock_yaml_loader.assert_called_once_with("some/file.yaml")
        assert "unexpected keyword arguments" in str(e_info.value)
        assert "check_sheets_invalid" in str(e_info.value)

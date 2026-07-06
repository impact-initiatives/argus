from pathlib import Path

import pytest

from argus.config import settings
from argus.models.base_dataset import BaseDataset
from argus.models.base_dataset_schemas import BaseDatasetSchema
from argus.models.resolver import find_dataset_files
from argus.utils.yaml_loader import download_config
from src.argus.loaders.excel_loader import ExcelLoader
from tests.helpers import error_counter


@pytest.fixture
def valid_schema() -> BaseDatasetSchema:
    dataset_config_dir = download_config(settings.DATASET_CONFIG_DIR)
    result = find_dataset_files(dataset_config_dir, "jmmi_dataset", "en", "schema.yaml", "validators.yaml")
    assert result is not None
    dataset: BaseDataset = BaseDataset(
        schema_path=result["schema.yaml"], validator_path=result["validators.yaml"]
    )
    return dataset.schema


@pytest.fixture
def valid_file():
    return Path("src/tests/loader/jmmi_valid.xlsx")


@pytest.fixture
def valid_file_fuzzy():
    return Path("src/tests/loader/jmmi_valid_fuzzy.xlsx")


@pytest.fixture
def invalid_file_fuzzy():
    return Path("src/tests/loader/jmmi_invalid_fuzzy.xlsx")


class TestLoadData:
    def test_valid_file(self, valid_schema: BaseDatasetSchema, valid_file: Path):
        data, results = ExcelLoader(valid_schema).load(valid_file)
        assert len(results) == 0

    def test_valid_file_fuzzy(self, valid_schema: BaseDatasetSchema, valid_file_fuzzy: Path):
        data, results = ExcelLoader(valid_schema).load(valid_file_fuzzy)
        assert len(error_counter(results)) == 0
        assert len(data.unexpected_sheets) == 2
        assert len(results) == 1

    def test_invalid_file_fuzzy(self, valid_schema: BaseDatasetSchema, invalid_file_fuzzy: Path):
        data, results = ExcelLoader(valid_schema).load(invalid_file_fuzzy, True)
        assert len(error_counter(results)) == 3
        assert len(results) == 3

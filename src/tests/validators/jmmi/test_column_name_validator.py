from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest

from argus.loaders.base import DataColumnMap
from argus.loaders.base_excel_loader import ExcelLoaderData
from argus.loaders.excel_loader import DataSheetMap
from argus.validators.base import BaseValidator
from argus.validators.jmmi.column_name_validator import (
    JMMIColumnNameCheck,
)
from tests.helpers import do_basic_checks


@pytest.fixture
def validator():
    """Create a UniqueColumn validator instance"""
    return JMMIColumnNameCheck()


def create_loader_data(column: str):
    df = pl.DataFrame({column: [1, 2, 3, 4, 5], "country": ["ssd", "ssd", "ssd", "ssd", "ssd"]})

    loaded_sheet = [
        DataSheetMap(
            schema_sheet_name="clean_data",
            data_sheet_name="clean_data",
            column_map=[DataColumnMap(schema_column_name="country", data_column_name="country")],
            data=df,
        ),
        DataSheetMap(
            schema_sheet_name="raw_data",
            data_sheet_name="raw_data",
            data=df,
        ),
    ]

    return ExcelLoaderData(loaded_sheets=loaded_sheet)


MOCK_FILE_DATA = {
    "iso_codes.yaml": ["ssd", "afg"],
    "suffix_list.yaml": ["yn", "so"],
    "items.yaml": ["egg", "chicken_meat"],
    "item_variables.yaml": ["availability_in_3_months_item"],
    "currency_codes.yaml": ["AED"],
}


def make_fake_load_file(data):
    """Factory function that returns a side_effect for patching."""

    def _fake(file_path, file_name):
        return data[file_name]

    return _fake


class TestColumnNames:
    def test_valid_standardised_variable(self, validator: BaseValidator):
        data = create_loader_data("chicken_meat_availability_in_3_months_item")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 0)

    def test_valid_country_variable(self, validator: BaseValidator):
        data = create_loader_data("ssd_chicken_meat_availability_in_4_months_item_yn")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 0)

    def test_valid_country_variable_valid_post_suffix(self, validator: BaseValidator):
        data = create_loader_data("ssd_availability_in_4_months_item_yn.chicken_meat")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 0)

    def test_valid_country_variable_invalid_post_suffix(self, validator: BaseValidator):
        data = create_loader_data("ssd_availability_in_4_months_item_yn.kangaroo_meat")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 1)
            assert results[0].details is not None
            assert len(results[0].details["sheet"]) == 1

    def test_country_variable_missing_prefix(self, validator: BaseValidator):
        data = create_loader_data("chicken_meat_availability_in_4_months_item_yn")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 1)
            assert results[0].details is not None
            assert len(results[0].details["sheet"]) == 1

    def test_country_variable_missing_suffix(self, validator: BaseValidator):
        data = create_loader_data("ssd_chicken_meat_availability_in_4_months_item")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 1)
            assert results[0].details is not None
            assert len(results[0].details["sheet"]) == 1

    def test_country_variable_unknown_suffix(self, validator: BaseValidator):
        data = create_loader_data("ssd_chicken_meat_availability_in_4_months_item_ynn")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 1)
            assert results[0].details is not None
            assert len(results[0].details["sheet"]) == 1

    def test_country_variable_unknown_prefix(self, validator: BaseValidator):
        data = create_loader_data("sssd_chicken_meat_availability_in_4_months_item_yn")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 1)
            assert results[0].details is not None
            assert len(results[0].details["sheet"]) == 1

    def test_valid_country_standardisable_variable(self, validator: BaseValidator):
        data = create_loader_data("ssd_chicken_meat_availability_in_3_months_item_yn")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 1)
            assert results[0].details is not None
            assert len(results[0].details["sheet"]) == 1

    def test_valid_unknown_item(self, validator: BaseValidator):
        data = create_loader_data("kangaroo_meat_availability_in_3_months_item")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 1)
            assert results[0].details is not None
            assert len(results[0].details["sheet"]) == 1

    def test_invalid_standardised_variable(self, validator: BaseValidator):
        data = create_loader_data("chicken_meat_3_months_availability_item")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 1)
            assert results[0].details is not None
            assert len(results[0].details["sheet"]) == 1

    def test_invalid_standardised_variable_and_item(self, validator: BaseValidator):
        data = create_loader_data("kangaroo_meat_3_months_availability_item")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 2)
            assert results[0].details is not None
            assert len(results[0].details["sheet"]) == 1
            assert results[1].details is not None
            assert len(results[1].details["sheet"]) == 1

    def test_invalid_column(self, validator: BaseValidator):
        data = create_loader_data("deviceid")
        with patch.object(
            JMMIColumnNameCheck, "_load_file", side_effect=make_fake_load_file(MOCK_FILE_DATA)
        ):
            results = validator.validate(data, dataset_config_directory=Path("./some/location"))
            do_basic_checks(results, 1)
            assert results[0].details is not None
            assert len(results[0].details["sheet"]) == 2

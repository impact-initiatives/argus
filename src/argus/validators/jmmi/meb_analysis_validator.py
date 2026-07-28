from pathlib import Path

import polars as pl

from ...loaders.base_excel_loader import ExcelLoaderData
from ...validators.base import BaseValidator, SeverityLevel, ValidationResult
from ...validators.data_helpers import (
    get_data_loaded_sheets,
)


class JMMIMebAnalysisCheck(BaseValidator):
    def __init__(
        self,
        meb_analysis_sheet: str = "meb_analysis",
        clean_data_sheet: str = "clean_data",
        column_suffix_check_list: list[str] | None = None,
        numeric_column_suffix_check_list: list[str] | None = None,
    ):

        self.meb_analysis_sheet: str = meb_analysis_sheet
        self.clean_data_sheet: str = clean_data_sheet
        self.column_suffix_check_list = (
            column_suffix_check_list
            if column_suffix_check_list is not None
            else ["local_currency", "usd_xrate_official"]
        )
        self.numeric_column_suffix_check_list = (
            numeric_column_suffix_check_list
            if numeric_column_suffix_check_list is not None
            else ["currency", "official", "parallel", "year"]
        )

    @property
    def name(self) -> str:
        return "JMMIMebAnalysisCheck"

    def validate(
        self, data: ExcelLoaderData, **kwargs: str | int | float | Path
    ) -> list[ValidationResult]:
        """Validates the column names for JMMI meb_analysis sheets.

        JMMI datasets have standardised naming conventions. This checks the follwoing rules:
        - there are at least two columns ending in "_local_currency" and "usd_xrate_official"
        - numeric variables should only end "_currency", "official","parallel", "year”
            - also checks if there are non-numeric variables with these suffixes

        Args:
            data (ExcelLoaderData): data (ExcelLoaderData): data to be validated

        Returns:
            list[ValidationResult]: a list of validation results
        """

        results: list[ValidationResult] = []
        # C003
        expected_suffixes_found: int = 2

        result, data_loaded_sheets = get_data_loaded_sheets(
            data=data,
            sheet_names=[self.meb_analysis_sheet, self.clean_data_sheet],
            rule=self.name,
        )

        if result is not None:
            results.append(result)
            return results

        # C003: in the MEB tab there are at least 2 columns ending in
        # "_local_currency" and "usd_xrate_official"
        meb_analysis_columns = data_loaded_sheets[self.meb_analysis_sheet].data.columns
        column_suffix_check_list_found = [
            column
            for column in meb_analysis_columns
            if any(prefix in column for prefix in self.column_suffix_check_list)
        ]

        if len(column_suffix_check_list_found) < expected_suffixes_found:
            results.append(
                ValidationResult(
                    rule=self.name,
                    message=self._(
                        "jmmi_meb_analysis_validator.suffix_check",
                        count=len(column_suffix_check_list_found),
                        no_expected=expected_suffixes_found,
                        expected_suffixes=", ".join(
                            f"'{item}'" for item in self.column_suffix_check_list
                        ),
                        sheet=self.meb_analysis_sheet,
                    ),
                    severity=SeverityLevel.ERROR,
                )
            )

        # C005
        # columns with a numeric suffix
        meb_column_suffix_check_list_found = [
            column
            for column in meb_analysis_columns
            if any(
                suffix in column.split("_")[-1] for suffix in self.numeric_column_suffix_check_list
            )
        ]

        meb_numeric_columns = (
            data_loaded_sheets[self.meb_analysis_sheet].data.select(pl.selectors.numeric()).columns
        )

        # numeric columns without suffix
        meb_numeric_column_missing_suffix = [
            column
            for column in meb_numeric_columns
            if not any(
                suffix in column.split("_")[-1] for suffix in self.numeric_column_suffix_check_list
            )
        ]

        # columns with suffix but not numeric
        meb_non_numeric_column_with_suffix = [
            column
            for column in meb_column_suffix_check_list_found
            if column not in meb_numeric_columns
        ]

        if meb_numeric_column_missing_suffix:
            results.append(
                ValidationResult(
                    rule=self.name,
                    message=self._(
                        "jmmi_meb_analysis_validator.numeric_suffix_check",
                        count=len(meb_numeric_column_missing_suffix),
                        expected_suffixes=", ".join(
                            f"'{item}'" for item in self.numeric_column_suffix_check_list
                        ),
                        sheet=self.meb_analysis_sheet,
                    ),
                    severity=SeverityLevel.ERROR,
                    details={"numeric columns without suffix": meb_numeric_column_missing_suffix},
                )
            )

        if meb_non_numeric_column_with_suffix:
            results.append(
                ValidationResult(
                    rule=self.name,
                    message=self._(
                        "jmmi_meb_analysis_validator.numeric_suffix_check_non_numeric_columns",
                        count=len(meb_non_numeric_column_with_suffix),
                        sheet=self.meb_analysis_sheet,
                    ),
                    severity=SeverityLevel.ERROR,
                    details={
                        "non-numeric columns with numeric suffix": meb_non_numeric_column_with_suffix
                    },
                )
            )

        return results

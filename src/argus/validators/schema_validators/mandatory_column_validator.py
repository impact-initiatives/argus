import polars as pl

from ...loaders.base_excel_loader import ExcelLoaderData
from ...models.base_dataset_schemas import BaseDatasetSchema
from ...validators.base import BaseValidator, SeverityLevel, ValidationResult
from ..data_helpers import get_data_loaded_columns, get_data_loaded_sheets


class MandatoryColumnsCheck(BaseValidator):
    @property
    def name(self) -> str:
        return "MandatoryColumnsCheck"

    def __init__(self, schema: BaseDatasetSchema):
        self.schema = schema

    def validate(self, data: ExcelLoaderData) -> list[ValidationResult]:
        """Checks to see if any expected mandatory columns are missing
        across relevant sheets.

        Also checks if unique columns are missing.

        Args:
            data (ExcelLoaderData): data to be validated

        Returns:
            List[ValidationResult]: List of validation errors.
        """
        results: list[ValidationResult] = []

        result, data_loaded_sheets = get_data_loaded_sheets(
            data=data,
            sheet_names=self.schema.get_loaded_sheets_standard_names(required=True),
            rule=self.name,
        )
        # if optional sheets have been loaded, check their columns
        result_optional, data_loaded_sheets_optional = get_data_loaded_sheets(
            data=data,
            sheet_names=self.schema.get_loaded_sheets_standard_names(required=False),
            rule=self.name,
        )

        if data_loaded_sheets_optional:
            data_loaded_sheets.update(data_loaded_sheets_optional)

        if result is not None:
            if result.details is None:
                result.details = {"missing_sheets": [result.sheet_name]}

            results.append(
                ValidationResult(
                    rule=self.name,
                    message=self._(
                        "mandatory_column_validator.missing_sheets",
                        count=len(result.details["missing_sheets"]),
                    ),
                    severity=SeverityLevel.ERROR,
                    details=result.details,
                )
            )

            return results

        for sheet, loaded_sheet in data_loaded_sheets.items():
            # get all the columns expected for the sheet
            search_columns = self.schema.get_sheet_column_standard_names(sheet)
            # sheet it checked above
            assert search_columns is not None

            search_items = {key: loaded_sheet for key in search_columns}

            # try to get all the loaded columns
            result, columns = get_data_loaded_columns(search_items, self.name)

            if result is not None:
                result.sheet_name = loaded_sheet.data_sheet_name
                results.append(result)

        if results:
            column_dict: list[dict[str, str]] = [{}]

            for item in results:
                if item.details is None:
                    column_dict.append(
                        {
                            "sheet_name": item.sheet_name if item.sheet_name is not None else "",
                            "column_name": item.column_name if item.column_name is not None else "",
                        }
                    )
                else:
                    for _, d_columns in item.details.items():
                        for d_column in d_columns:
                            column_dict.append(
                                {
                                    "sheet_name": item.sheet_name
                                    if item.sheet_name is not None
                                    else "",
                                    "column_name": d_column,
                                }
                            )

            column_df = pl.DataFrame(column_dict, schema=["sheet_name", "column_name"]).to_dict(
                as_series=False
            )
            result = ValidationResult(
                rule=self.name,
                message=self._("mandatory_column_validator.mandatory_columns", count=len(results)),
                severity=SeverityLevel.ERROR,
                details=column_df,
            )
            return [result]

        return results

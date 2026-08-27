from ..common.list_matching import duplicate_list_items
from ..validators.base import SeverityLevel, ValidationResult
from .base_dataset_schemas import BaseDatasetSchema


def validate_schema(schema: BaseDatasetSchema) -> list[ValidationResult]:
    """Checks that a sheet is listed only once in the schema.

    Checks that a column is listed only once per sheet. This check
    does not include unique columns as they are likely included
    in mandatory columns and only one unique column can be set

    Args:
        schema (BaseDatasetSchema): schema to validate

    Returns:
        List[ValidationResult]: validation errors
    """
    sheet_names: list[str] = []
    results: list[ValidationResult] = []

    for sheet in schema.schema_loaded_sheets:
        sheet_names.extend(sheet.combine_sheet_names())
        column_names: list[str] = sheet.combine_column_names(return_unique_list=False)

        # check duplicate columns per sheet
        duplicate_column_names = duplicate_list_items(column_names)
        if duplicate_column_names:
            results.append(
                ValidationResult(
                    rule="Duplicate column names in schema sheet",
                    message=f" Sheet {sheet} for schema {schema.programme_type}"
                    + f" {schema.output_type} has mandatory column standard/altername names listed"
                    + " on more than one column. Column names should be unique per sheet."
                    + " Check the output for details.",
                    severity=SeverityLevel.ADMIN_ERROR,
                    column_name=", ".join(duplicate_column_names),
                    details={"columns": duplicate_column_names},
                )
            )
    for sheet in schema.schema_unloaded_sheets:
        sheet_names.extend(sheet.combine_sheet_names())

    duplicate_sheet_names = duplicate_list_items(sheet_names)
    if duplicate_sheet_names:
        results.append(
            ValidationResult(
                rule="Duplicate sheet names in schema.",
                message=f"The schema for {schema.programme_type} {schema.output_type} contains"
                + " sheet names that are listed for more than one sheet. Sheet names and"
                + " alternate sheet names should be unique to each schema."
                + " Check the output for details.",
                severity=SeverityLevel.ADMIN_ERROR,
                details={"sheets": duplicate_sheet_names},
            )
        )

    return results

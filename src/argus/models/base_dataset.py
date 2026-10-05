from pathlib import Path

from ..common.list_matching import filter_list
from ..config import settings
from ..loaders.base_excel_loader import ExcelLoaderData
from ..models.base import SheetClassification
from ..validators.base import BaseValidator, SortedSheets, ValidationResult
from ..validators.common_validators import (
    CleaningLogToCleanCheck,
    ConsentCheck,
    CrossSheetIdCheck,
    CrossSheetRowSumCheck,
    DataTypeCheck,
    NaNDataCheck,
    RawToCleanToLogCheck,
    SkipLogicCheck,
    SurveyChoicesCheck,
)
from .base_dataset_schemas import BaseDatasetSchema
from .resolver import ResolveDataset


class BaseDataset:
    def __init__(self, schema_path: Path | str, validator_path: Path | str) -> None:
        self.schema_path: Path | str = schema_path
        self.validator_path: Path | str = validator_path
        self.resolver: ResolveDataset = ResolveDataset()
        self.schema: BaseDatasetSchema = self.get_schema()
        self.validators: list[BaseValidator] = self.get_validators()
        self.data: ExcelLoaderData

    def get_schema(self) -> BaseDatasetSchema:
        schema = self.resolver.resolve_schema(self.schema_path)
        return schema

    def get_validators(self) -> list[BaseValidator]:
        return self.resolver.resolve_validators(self.validator_path, self.schema)

    def process_data(self, **kwargs: int | str | float | Path) -> list[ValidationResult]:
        return []

    def build_validators(self):
        """
        Build all the sheet specific common validators.
        This assumes all the relationships are properly defined
        in the schema.
        """
        sorted_sheets: SortedSheets = SortedSheets()
        parent_clean_sheet = None

        for sheet in self.schema.schema_loaded_sheets:
            if (
                sheet.classification == SheetClassification.CLEANING_LOG_SHEET
                and sheet.parent_sheet is not None
            ):
                # cleaning log in clean
                self.validators.append(
                    CrossSheetIdCheck(
                        schema=self.schema,
                        master_sheet=sheet.parent_sheet,
                        child_sheets=[sheet.standard_name],
                    )
                )

                self.validators.append(
                    CleaningLogToCleanCheck(
                        schema=self.schema,
                        cleaning_log_sheet=sheet.standard_name,
                        clean_data_sheet=sheet.parent_sheet,
                    )
                )

                log_parent_clean_sheet = self.schema.get_schema_loaded_sheet(sheet.parent_sheet)

                # clean sheet and its linked raw sheet
                if (
                    log_parent_clean_sheet is not None
                    and log_parent_clean_sheet.linked_sheet is not None
                ):
                    self.validators.append(
                        RawToCleanToLogCheck(
                            schema=self.schema,
                            cleaning_log_sheet=sheet.standard_name,
                            clean_data_sheet=sheet.parent_sheet,
                            raw_data_sheet=log_parent_clean_sheet.linked_sheet,
                        )
                    )

            if sheet.classification == SheetClassification.DELETION_LOG_SHEET:
                if sheet.parent_sheet is not None:
                    parent_raw_sheet = self.schema.get_schema_loaded_sheet(sheet.parent_sheet)
                    if parent_raw_sheet is not None and parent_raw_sheet.linked_sheet is not None:
                        self.validators.append(
                            CrossSheetRowSumCheck(
                                schema=self.schema,
                                master_sheet=parent_raw_sheet.standard_name,
                                child_sheets=[parent_raw_sheet.linked_sheet, sheet.standard_name],
                                master_deletion_log=None,
                            )
                        )
                        # clean and deletion log in raw
                        self.validators.append(
                            CrossSheetIdCheck(
                                schema=self.schema,
                                master_sheet=parent_raw_sheet.standard_name,
                                child_sheets=[parent_raw_sheet.linked_sheet, sheet.standard_name],
                            )
                        )

                        clean_sheet = self.schema.get_schema_loaded_sheet(
                            parent_raw_sheet.linked_sheet
                        )
                        if clean_sheet is not None and clean_sheet.linked_log is not None:
                            # cleaning log not in deletion log
                            self.validators.append(
                                CrossSheetIdCheck(
                                    schema=self.schema,
                                    master_sheet=clean_sheet.linked_log,
                                    child_sheets=[sheet.standard_name],
                                    is_in=False,
                                )
                            )

            elif sheet.classification == SheetClassification.CLEAN_DATA_SHEET:
                sorted_sheets.clean_sheets.append(sheet.standard_name)
                # child in parent
                if sheet.parent_sheet is not None:
                    self.validators.append(
                        CrossSheetIdCheck(
                            schema=self.schema,
                            master_sheet=sheet.parent_sheet,
                            child_sheets=[sheet.standard_name],
                        )
                    )
                else:
                    # all child sheets should have the same parent
                    parent_clean_sheet = sheet.standard_name

            elif sheet.classification == SheetClassification.RAW_DATA_SHEET:
                # child in parent
                if sheet.parent_sheet is not None:
                    self.validators.append(
                        CrossSheetIdCheck(
                            schema=self.schema,
                            master_sheet=sheet.parent_sheet,
                            child_sheets=[sheet.standard_name],
                        )
                    )

                if sheet.parent_sheet is None and sheet.linked_sheet is not None:
                    self.validators.append(
                        ConsentCheck(
                            schema=self.schema,
                            raw_data_sheet=sheet.standard_name,
                            clean_data_sheet=sheet.linked_sheet,
                        )
                    )

        if sorted_sheets.clean_sheets:
            self.validators.append(
                NaNDataCheck(schema=self.schema, check_sheets=sorted_sheets.clean_sheets)
            )

            if self.schema.get_schema_loaded_sheet(settings.SURVEY_SHEET_NAME) is not None:
                self.validators.append(
                    DataTypeCheck(schema=self.schema, check_sheets=sorted_sheets.clean_sheets)
                )

                if parent_clean_sheet is not None:
                    self.validators.append(
                        SkipLogicCheck(
                            schema=self.schema,
                            parent_sheet=parent_clean_sheet,
                            child_sheets=filter_list(
                                sorted_sheets.clean_sheets, [parent_clean_sheet]
                            ),
                        )
                    )

                if self.schema.get_schema_loaded_sheet(settings.CHOICES_SHEET_NAME) is not None:
                    self.validators.append(
                        SurveyChoicesCheck(
                            schema=self.schema, check_sheets=sorted_sheets.clean_sheets
                        )
                    )

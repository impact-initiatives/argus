from dataclasses import dataclass, field
from typing import override

from ..models.base_dataset import BaseDataset
from ..validators.base import BaseValidator
from ..validators.data_validators import (
    CleaningLogToClean,
    ConsentCheck,
    CrossSheetIdCheck,
    CrossSheetRowSumCheck,
    DataTypeCheck,
    NaNDataCheck,
    PiiDataCheck,
    RawToCleanToLog,
    SurveyChoicesCheck,
    UniqueColumn,
)
from ..validators.schema_validators import (
    ColumnNameCheck,
    DuplicateSheetMatches,
    MandatoryColumns,
    MissingSheetsCheck,
    UnexpectedSheetsCheck,
)
from .base import SchemaSheetMap
from .base_dataset_schemas import BaseDatasetSchema
from .defaults import (
    CHOICES_SHEET,
    CLEAN_DATA_SHEET,
    DELETION_LOG_SHEET,
    RAW_DATA_SHEET,
    READ_ME_SHEET,
    SAMPLING_INFO_SHEET,
    SURVEY_SHEET,
    create_cleaning_log_sheet,
    create_enumerator_performance_sheet,
    create_variable_tracker_sheet,
)


@dataclass()
class JMMIDatasetSchema(BaseDatasetSchema):
    dataset_type: str = "JMMI"

    schema_loaded_sheets: list[SchemaSheetMap] = field(
        default_factory=lambda: [
            RAW_DATA_SHEET,
            CLEAN_DATA_SHEET,
            create_cleaning_log_sheet(
                standard_name="cleaning_log",
                id_column="uuid",
                id_column_alt=["_uuid"],
                alternate_names=["clog_logbook"],
            ),
            SURVEY_SHEET,
            CHOICES_SHEET,
            DELETION_LOG_SHEET,
            create_variable_tracker_sheet(alternate_names=["clog_variable_tracker"]),
        ]
    )

    schema_unloaded_sheets: list[SchemaSheetMap] = field(
        default_factory=lambda: [
            READ_ME_SHEET,
            SAMPLING_INFO_SHEET,
            create_enumerator_performance_sheet(alternate_names=["clog_enum_performance"]),
            SchemaSheetMap(standard_name="meb_analysis"),
            SchemaSheetMap(standard_name="mfs_analysis"),
        ]
    )


# schema and validation rules for jmmi dataset.
class JMMIDataset(BaseDataset):
    def __init__(self) -> None:
        self.schema: BaseDatasetSchema = self.get_schema()
        self.validators: list[BaseValidator] = self.get_validators()

    @override
    def get_schema(self, *args: str | int | float, **kwargs: str | int | float):
        schema = JMMIDatasetSchema()
        self.lower_schema(schema)
        return schema

    @override
    def get_validators(
        self, *args: str | int | float, **kwargs: str | int | float
    ) -> list[BaseValidator]:
        return [
            MissingSheetsCheck(schema=self.schema),
            UnexpectedSheetsCheck(),
            DuplicateSheetMatches(),
            MandatoryColumns(schema=self.schema),
            UniqueColumn(schema=self.schema),
            PiiDataCheck(schema=self.schema),
            CrossSheetRowSumCheck(schema=self.schema),
            CrossSheetIdCheck(schema=self.schema),
            CrossSheetIdCheck(
                schema=self.schema, master_sheet="clean_data", child_sheets=["cleaning_log"]
            ),
            CleaningLogToClean(schema=self.schema),
            RawToCleanToLog(schema=self.schema),
            NaNDataCheck(schema=self.schema),
            ConsentCheck(schema=self.schema),
            ColumnNameCheck(),
            DataTypeCheck(schema=self.schema),
            SurveyChoicesCheck(schema=self.schema),
        ]

    @override
    def process_data(self):
        return super().process_data()

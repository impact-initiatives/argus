from abc import abstractmethod
from pathlib import Path

from ..loaders.base_excel_loader import ExcelLoaderData
from ..models.preprocess import lowercase_schema_mappings
from ..validators.base import BaseValidator, ValidationResult
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
        lowercase_schema_mappings(schema)
        return schema

    def get_validators(self) -> list[BaseValidator]:
        return self.resolver.resolve_validators(self.validator_path, self.schema)

    @abstractmethod
    def process_data(self) -> list[ValidationResult]:
        pass

import argparse
from pathlib import Path

from argus.config import settings
from src.argus.orchestrator.validation_pipeline import ValidationPipeline


def main():
    parser = argparse.ArgumentParser(description="Data Validation Framework")
    parser.add_argument("input_file", type=Path, help="Path to Excel file")
    parser.add_argument(
        "--dataset-type",
        required=True,
        choices=["jmmi", "other"],
        help="Type of dataset to validate",
    )

    args = parser.parse_args()

    pipeline = ValidationPipeline()
    results = pipeline.run_all(args.input_file, dataset_type=args.dataset_type)
    print(results)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        settings.logger.log_exception(e)

    exit()

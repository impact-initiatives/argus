**Argus**: A flexible framework that can quickly process and validate standardised and less-standardised datasets.

## Overview
Argus is designed to allow for the review and validation of different excel based datasets. This is performed through the construction of a dataset schema and specifying a list of validation rules that are required to be run against the data. 

Both the schema components and the validation components are designed to be modular. This helps to support the easy building and management of schemas, validation rules and their integration with the wider validation framework.

Argus can be run as a standalone tool or incorporated into other workflows.

### Supported Datasets
To run the process a dataset must be specidifed. The current supported datasets and their parameter values include:

| **Dataset** | **parameter Value** |
| --- | --- | 
|JMMI|jmmi|
|All other datasets| other

## Setup
1. Clone the repository
2. Install dependencies with [uv](https://github.com/astral-sh/uv):
```bash
   uv sync
```
3. Download a dataset. Some publicly available options include:
- [jmmi](https://repository.impact-initiatives.org/document/impact/031f3c9b/REACH_SSD_Dataset-Analysis_JMMI_March-2026.xlsx)
- [other](https://repository.impact-initiatives.org/document/impact/d77de3de/KEN_2401_MSNA_data_camps.xlsx)

4. Run the process
```bash
uv run main.py --dataset-type jmmi "path/to/excel/file.xlsx"
```
or
```bash
uv run main.py --dataset-type other "path/to/excel/file.xlsx"
```
5. Any validation errors will be returned in JSON format:
```json
{
   "success": bool,
   "summary": {
         // counts of the severities of the validation results
      "error": int,
      "warning": int,
      "info": int,
      "passed": int,
      "admin_error": int,
      "admin_info": int,
   },
   // details of all the validation results
   "error":       [...],  
   "warning":     [...],  
   "info":        [...],
   "passed":      [...],  
   "admin_error": [...],  
   "admin_info":  [...],  
   "metadata": {
      "dataset_type": str,
   },
}
```

### Integration with other projects or workflows
If incorporating this into another project or workflow it is probably easier to use the orchestrator directly:
```python
from src.argus.orchestrator.validation_pipeline import ValidationPipeline

try:
   results = ValidationPipeline().run_all(filepath="path/to/excel/file.xlsx", dataset_type="other", locale='en') #or jmmi
except Exception as e:
   # handle errors
   print(e)
   
# process results
```
### Validation Message Types
There are several error types that can be returned:
- **Admin errors**: these are likely either Python errors or schema design errors.
- **Admin info**: Information about dynamic schema generation or other information that could be useful for debugging.
- **Errors**: critical errors from the validation process. Eg: a missing sheet.
- **Warnings**: warnings from the validation process. Eg: an optional sheet is missing, possible PII column found.
- **Info**: information for user awareness. Eg: if fuzzy matching was used to match a column.
- **Passed**: validation rules that passed without any errors.

### Validation Message Translations
Most user messages (Error, Warnings, Info, Passed) support translations into other languages. This is a work in progress. If a message is not available for a specific language, the message will default to English. 

See [translations](locales/README.md) for details on managing/expanding these.

### Running Rules Individually
If testing or debugging, it is possible to run individual validation rules. To do this, first load the data setting the appropriate filepath and then run the required rule. For JMMI:

```python
from src.argus.models.jmmi import JMMIDataset
from src.argus.loaders.excel_loader import ExcelLoader
# use whichever rule is required
from src.argus.validators.data_validators import RawToCleanToLog

schema = JMMIDataset().schema
loader = ExcelLoader(schema)
data, results = loader.load("path/to/excel/file.xlsx")

# run the required rule setting the appropriate parameters
results = RawToCleanToLog(schema=schema).validate(data=data)
# review results

```
or for other datasets:
```python
from src.argus.models.dynamic_model import DynamicDataset
from src.argus.loaders.excel_loader import ExcelLoader
# Use whichever rule is required
from src.argus.validators.data_validators import CrossSheetIdCheck

dataset = DynamicDataset()
loader = ExcelLoader(dataset.schema)
dataset.data, excel_results = loader.load("path/to/excel/file.xlsx",
                                            load_all_sheets= True  )
dataset.process_data()

# run the required rule setting the appropriate parameters
results = CrossSheetIdCheck(dataset.schema).validate(dataset.data)
# review results
```
## Contributing and Reporting Issues
If you are interested in expanding the list of supported languages for the validation messages get in touch. 

If you encounter any bugs report these on the [project issues page](https://github.com/impact-initiatives/argus/issues).
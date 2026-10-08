# A Dependency-Driven Framework for Frequent Itemset Mining in Relational Databases

This repository contains the source code for the paper **"A Dependency-Driven Framework for Frequent Itemset Mining in Relational Databases"**, submitted to the *Knowledge and Information Systems (KAIS)* journal.

## 1. Project Structure

```text
.
├── data/               # Input datasets (CSV format)
├── results/            # JSON execution logs and results
├── Framework_RQFP.py   # Proposed Framework (using RQFP)
├── Framework_FPG.py    # Proposed Framework (using FP-Growth)
├── RQFP.py             # Baseline RQFP algorithm
├── FP_Growth.py        # Baseline FP-Growth algorithm
├── requirements.txt    # Required dependencies
└── CITATION.cff        # Citation metadata
```

## 2. Installation & Prerequisites

- **Python Version:** Python 3.8 or higher.
- **Dependencies:** The codebase relies strictly on the Python Standard Library (`csv`, `json`, `os`, `time`, `itertools`, `collections`, `argparse`, `tracemalloc`, `logging`). No external packages are required.

To verify or install dependencies:

```bash
pip install -r requirements.txt
```

## 3. Usage & Execution

All scripts accept structured command-line arguments and automatically output performance summaries in JSON format.

### 3.1. Running the Proposed Framework

- **With RQFP:**

```bash
python Framework_RQFP.py --dataset ./data/adult1.csv --support 0.3
```

- **With FP-Growth:**

```bash
python Framework_FPG.py --dataset ./data/adult1.csv --support 0.3
```

### 3.2. Running the Baseline Algorithms

- **Baseline RQFP:**

```bash
python RQFP.py --dataset ./data/adult1.csv --support 0.3
```

- **Baseline FP-Growth:**

```bash
python FP_Growth.py --dataset ./data/adult1.csv --support 0.3
```

## 4. Command-Line Arguments

| Argument | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `--dataset` | `str` | `./data/adult1.csv` | Relative or absolute path to the input CSV dataset. |
| `--support` | `float` | `0.3` | Minimum support threshold (0.0 <= s <= 1.0). |
| `--max_rows` | `int` | `None` | Optional limit on the number of rows to process. |
| `--result` | `str` | `results/*.json` | Destination path for runtime and memory JSON log. |

## 5. Output Format

Results are logged in structured JSON format under the `results/` directory, detailing:

- Total execution time (seconds)
- Peak memory usage (MB)
- Extracted frequent itemsets count
- Algorithmic phase breakdowns (where applicable)

## 6. Citation

If you use this code or framework in your research, please cite our paper using the metadata provided in `CITATION.cff`.

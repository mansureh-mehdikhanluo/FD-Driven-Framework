# FD-Driven-Framework

A dependency-driven framework for frequent itemset mining in relational databases.

## Overview

Frequent itemset mining is a fundamental task in data mining aimed at discovering associations and correlations among data items. It has important applications in market basket analysis, web usage mining, and bioinformatics. Despite its broad applicability, mining frequent itemsets remains computationally challenging due to two major issues:

1. **Exponential search-space growth** as the number of items increases.
2. **High memory consumption** during candidate generation and intermediate structure maintenance.

Classical algorithms such as **Apriori** reduce the number of candidate itemsets through iterative pruning, but require repeated database scans. In contrast, **FP-Growth** compresses the database into an FP-tree and performs mining in memory, reducing I/O overhead. However, both approaches generally assume a transaction-oriented view of data and ignore the rich structural information available in **relational databases**, such as attribute dependencies and integrity constraints.

This repository provides an implementation of a **dependency-driven framework** that incorporates relational dependencies into the frequent itemset mining process. The framework aims to reduce redundancy, partition the mining task into smaller components, and improve scalability in high-dimensional relational settings.

## Associated Paper

**A Dependency-Driven Framework for Frequent Itemset Mining in Relational Databases**

## Authors

- **Mansureh Mehdikhanluo**
- **Mahmoud Shirazi**
- **Zahra Narimani**

## Repository Structure

```text
FD-Driven-Framework/
├── .gitignore
├── CITATION.cff
├── LICENSE
├── README.md
├── requirements.txt
├── data/
│   └── adult1.csv
└── scripts/
├── FP_Growth.py
├── Framework_FPG.py
├── Framework_RQFP.py
└── RQFP.py
```

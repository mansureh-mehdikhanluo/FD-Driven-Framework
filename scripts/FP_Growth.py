import logging
import time
import csv
import tracemalloc
import os
import json
from typing import Optional
import argparse

# Node class for FP-tree
class Node:
    def __init__(self, item, count=0):
        self.item = item
        self.count = count
        self.parent = None
        self.children = {}

    def __str__(self):
        if self.item is not None:
            s = f'item: {self.item} count: {self.count}  '
        else:
            s = 'root \n'
        s += 'children: '
        for child in self.children:
            s += str(child) + ' '
        return s

# FP-tree class
class FPTree:
    def __init__(self):
        # header_table: dict[item] = [Node1, Node2...]
        self.header_table = {}
        self.item_counter = {}
        self.root = Node(None)

    # Add a transaction to the tree
    def add_tran(self, tran, weight=1):
        ptr = self.root
        for item in tran:
            if item in ptr.children:
                ptr.children[item].count += weight
                self.item_counter[item] += weight
                ptr = ptr.children[item]
            else:
                new_node = Node(item, weight)
                new_node.parent = ptr
                ptr.children[item] = new_node
                if item in self.header_table:
                    self.header_table[item].append(new_node)
                    self.item_counter[item] += weight
                else:
                    self.header_table[item] = [new_node]
                    self.item_counter[item] = weight
                ptr = new_node

    # Mine frequent patterns from the tree
    def mine(self, min_cnt=1):
        fp, fp_count = [], []
        for item in self.header_table:
            if self.item_counter[item] >= min_cnt:
                fp.append([item])
                fp_count.append(self.item_counter[item])

                cond_trans, weights = self.get_conditional_tran(item, min_cnt)
                cond_tree = FPTree()
                for tran, weight in zip(cond_trans, weights):
                    assert item not in tran, (item, tran, weight)
                    cond_tree.add_tran(tran, weight)
                cond_fp, cond_fp_count = cond_tree.mine(min_cnt)
                if cond_fp:
                    cond_fp = [i + [item] for i in cond_fp]
                    fp += cond_fp
                    fp_count += cond_fp_count

        assert len(fp) == len(fp_count)
        if fp:
            fp = [sorted(i) for i in fp]
            tmp = list(zip(fp, fp_count))
            tmp = sorted(tmp, key=lambda x: (len(x[0]), x[0]))
            fp, fp_count = list(zip(*tmp))

        return fp, fp_count

    # Get conditional transactions for an item
    def get_conditional_tran(self, item, min_cnt=1):
        trans, weights = [], []
        for node in self.header_table[item]:
            tmp_tran = []
            ptr = node.parent
            while ptr.item is not None:
                tmp_tran.append(ptr.item)
                ptr = ptr.parent
            if tmp_tran:
                trans.append(tmp_tran)
                weights.append(node.count)
        return trans, weights

    # Print the tree structure
    def print_tree(self):
        l = [self.root]
        while l:
            next_l = []
            for node in l:
                print(node)
                next_l += node.children.values()
            l = next_l
            print('----------------------------------')

# FP-growth algorithm
def fp_growth(trans, min_cnt, use_log=False):
    """
    FP growth algorithm for frequent patterns mining

    Arguments:
        trans: list of transactions (each transaction is a list of items)
        min_cnt: minimum support count
        use_log: if True, enable logging

    Return:
        list of (pattern, frequency) tuples
    """
    if use_log:
        logging.basicConfig(
            filename='fp_tree.log',
            format='%(asctime)s %(message)s',
            level=logging.DEBUG,
            datefmt='%Y/%m/%d %I:%M:%S %p'
        )

    if use_log:
        logging.info('Begin to count items')

    # Count item frequency
    counter = {}
    for tran in trans:
        for item in tran:
            counter[item] = counter.get(item, 0) + 1

    if use_log:
        logging.info('Counting finished')

    frequent_item = [item for item in counter if counter[item] >= min_cnt]

    # Build FP-tree
    fp_tree = FPTree()
    if use_log:
        logging.info('Begin to add transactions')

    for tran in trans:
        tran = [item for item in tran if item in frequent_item]
        tran = list(set(tran))
        tran = sorted(tran, key=lambda x: (counter[x], x), reverse=True)
        if tran:
            fp_tree.add_tran(tran)

    if use_log:
        logging.info('Adding transactions finished')
        logging.info('Begin to mine fp')

    res = fp_tree.mine(min_cnt)
    res = list(zip(*res))

    if use_log:
        logging.info('Mining fp finished')

    return res


def preprocessing_csv(path_in: str, path_out: str, max_rows: Optional[int] = None) -> int:
    Start1=time.time()
    transactions = []
    n_trans = 0
    out_dir = os.path.dirname(path_out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(path_in, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if max_rows is not None and idx >= max_rows:
                break
            items = [
                f"{col}={val.strip()}"
                for col, val in row.items()
                if val.strip() != "" and val.strip() != "?"
            ]
            if items:
                transactions.append(items)
    with open(path_out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["transaction"])

        for item in transactions:
            if item:
                writer.writerow([json.dumps(item, ensure_ascii=False)])
                n_trans += 1
    print(f"time 1: {time.time() - Start1}")
    return n_trans


def read_transactions_csv(path):
    transactions = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            transactions.append(json.loads(row["transaction"]))
    return transactions


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A Dependency-Driven Framework for FIM (FP-Growth)")
    parser.add_argument("--dataset", type=str, default="./data/adult1.csv", help="Path to input dataset (CSV)")
    parser.add_argument("--support", type=float, default=0.3, help="Minimum support threshold (0.0 to 1.0)")
    parser.add_argument("--out_dir", type=str, default="./sub-datasets", help="Directory for intermediate tables")
    parser.add_argument("--result", type=str, default="results/frequent_patterns_FPG.json", help="Path to save output patterns (JSON)")
    parser.add_argument("--output", type=str, default="output/transactions.csv", help="Path to save output patterns (JSON)")
    parser.add_argument("--max_rows", type=int, default=None, help="Maximum size of rows")
    args = parser.parse_args()

    tracemalloc.start()
    global_start = time.time()

    # Step 1: Preprocessing 
    print(f"--- 1. Preprocessing---")
    n_trans = preprocessing_csv(args.dataset, args.output, args.max_rows)

    t1 = time.time() - global_start
    _, peak_pre = tracemalloc.get_traced_memory()
    print(f"Preprocessing Peak Memory: {peak_pre / 1024 / 1024:.2f} MB\n")

    min_count = max(1, int(n_trans * args.support))
    print(f"Database Rows (R): {n_trans} | Min Support Count (minsup): {min_count}\n")

    # Step 2:  (Mining)
    print("--- 2. Mining   ---")
    tracemalloc.reset_peak()
    start_step2 = time.time()
    trans = read_transactions_csv(args.output)
    S = fp_growth(trans, min_count)
    t2 = time.time() - start_step2
    _, peak_mining = tracemalloc.get_traced_memory()
    print(f"Number Frequent Itemset: {len(S)}")
    print(f"Mining Peak Memory: {peak_mining / 1024 / 1024:.2f} MB\n")

    # Step 3: Export Results to JSON
    if args.output:
        os.makedirs(os.path.dirname(args.result), exist_ok=True)
        patterns_json = [
        {"pattern": pattern, "support": cnt}
        for pattern, cnt in S
        ]
        export_data = {
            "experiment_meta": {
                "dataset": args.dataset,
                "support_threshold": args.support,
                "min_support_count": min_count,
                "total_rows": n_trans,
                "execution_time_sec": {
                    "decomposition": round(t1, 4),
                    "local_mining": round(t2, 4),
                    "total": round(t1 + t2 , 4)
                }
            },
         "frequent_patterns": patterns_json
        }
        with open(args.result, "w", encoding="utf-8") as out_file:
            json.dump(export_data, out_file, indent=4, ensure_ascii=False)

    # Global Summary
    print("----------------- Execution Summary -----------------")
    print(f"Total Frequent Patterns: {len(S)}")
    print(f"Total Runtime: {t1 + t2 :.4f} seconds")
    
    _, peak_total = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"Total Peak Memory Usage: {peak_total / 1024 / 1024:.2f} MB")
    if args.output:
        print(f"Frequent patterns successfully exported to: {args.result}")
    print("-----------------------------------------------------")

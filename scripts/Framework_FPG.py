import csv
import os
import json
import time
import argparse
from collections import defaultdict, Counter
from itertools import chain, combinations
import tracemalloc

# ----------------- Utility -----------------
def power_set(items):
    """Generate powerset of a list."""
    return list(chain.from_iterable(combinations(items, r) for r in range(1, len(items)+1)))

# ----------------- FP-Growth -----------------
class Node:
    def __init__(self, item, count=0):
        self.item = item
        self.count = count
        self.parent = None
        self.children = {}

class FPTree:
    def __init__(self):
        self.header_table = {}
        self.item_counter = {}
        self.root = Node(None)

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

    def mine(self, min_cnt=1):
        fp, fp_count = [], []
        for item in self.header_table:
            if self.item_counter[item] >= min_cnt:
                fp.append([item])
                fp_count.append(self.item_counter[item])
                cond_trans, weights = self.get_conditional_tran(item)
                cond_tree = FPTree()
                for tran, weight in zip(cond_trans, weights):
                    cond_tree.add_tran(tran, weight)
                cond_fp, cond_fp_count = cond_tree.mine(min_cnt)
                if cond_fp:
                    cond_fp = [i + [item] for i in cond_fp]
                    fp += cond_fp
                    fp_count += cond_fp_count
        if fp:
            fp = [sorted(i) for i in fp]
            tmp = list(zip(fp, fp_count))
            tmp = sorted(tmp, key=lambda x: (len(x[0]), x[0]))
            fp, fp_count = list(zip(*tmp))
        return fp, fp_count

    def get_conditional_tran(self, item):
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

def fp_growth(trans, min_cnt):
    counter = Counter()
    for tran in trans:
        for item in tran:
            counter[item] += 1
    frequent_item = [item for item in counter if counter[item] >= min_cnt]
    fp_tree = FPTree()
    for tran in trans:
        tran = [item for item in tran if item in frequent_item]
        tran = list(set(tran))
        tran = sorted(tran, key=lambda x: (counter[x], x), reverse=True)
        if tran:
            fp_tree.add_tran(tran)
    res = fp_tree.mine(min_cnt)
    res = list(zip(*res))
    return res

# ----------------- Preprocessing -----------------
def preprocessing1(lhs_fd, rhs_fd, csv_path, out_dir, band, max_rows=None):
    time_Start1 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    partitions = defaultdict(list)
    item_row_index = defaultdict(list)
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        header_eq = [h + "=" for h in header]
        for row_idx, row in enumerate(reader):
            if max_rows is not None and row_idx >= max_rows:
                break
            lhs_key = tuple(str(row[i]).strip() for i in lhs_fd)
            items = {}
            for col_idx, raw_val in enumerate(row):
                if not raw_val or raw_val == "?":
                    continue
                item = header_eq[col_idx] + str(raw_val).strip()
                items[col_idx] = item
                item_row_index[item].append(row_idx)
            partitions[lhs_key].append((row_idx, items))
    total_rows = sum(len(v) for v in partitions.values())

    candidate_cols = set(lhs_fd) | set(rhs_fd)
    num_subdatasets = 0
    small_transactions = []

    for lhs_key, rows in partitions.items():
        if len(rows) < band:
            for _, items in rows:
                small_transactions.append(list(items.values()))
            continue

        constant_items = []
        for c in candidate_cols:
            vals = {items.get(c) for _, items in rows}
            vals.discard(None)
            if len(vals) == 1:
                constant_items.append(vals.pop())

        powerset_items = list(chain.from_iterable(
            combinations(constant_items, r) for r in range(1, min(5, len(constant_items)) + 1)
        )) if constant_items else []
        const_set = set(constant_items)

        num_subdatasets += 1
        path = os.path.join(out_dir, f"subdataset_{num_subdatasets}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["transaction"])
            for _, items in rows:
                filtered = [it for it in items.values() if it not in const_set]
                writer.writerow([json.dumps(filtered, ensure_ascii=False)])
            if powerset_items:
                writer.writerow(["#POWERSET"])
                for ps in powerset_items:
                    writer.writerow([json.dumps([str(i) for i in ps], ensure_ascii=False)])
    if small_transactions:
        num_subdatasets += 1
        path = os.path.join(out_dir, f"subdataset_{num_subdatasets}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["transaction"])
            for t in small_transactions:
                writer.writerow([json.dumps([str(i) for i in t], ensure_ascii=False)])
    print(f"Time 1 (Preprocessing): {time.time() - time_Start1:.4f} s")
    return total_rows, num_subdatasets, dict(item_row_index)

# ----------------- Candidate Builder -----------------
def build_candidates_from_subdatasets(out_dir, min_supp, total_rows):
    time_Start2 = time.time()
    candida_FP = set()
    files = sorted(f for f in os.listdir(out_dir) if f.startswith("subdataset_") and f.endswith(".csv"))
    for filename in files:
        transactions = []
        powerset_items = []
        with open(os.path.join(out_dir, filename), newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            reading_powerset = False
            for row in reader:
                cell = row[0].strip()
                if not cell:
                    continue
                if cell == "#POWERSET":
                    reading_powerset = True
                    continue
                if reading_powerset:
                    powerset_items.append(frozenset(str(i) for i in json.loads(cell)))
                else:
                    transactions.append([str(i) for i in json.loads(cell)])

        r = len(transactions)
        if r == 0:
            continue

        new_min_sup = max(1, int(min_supp * r / total_rows))
        S = fp_growth(transactions, new_min_sup)
        FP_sets = [
            frozenset(str(i) for i in p[0]) if isinstance(p[0], (list, tuple)) else frozenset([str(p[0])])
            for p in S
        ]

        for x in FP_sets:
            candida_FP.add(tuple(sorted(x)))
        for y in powerset_items:
            candida_FP.add(tuple(sorted(y)))
        for x in FP_sets:
            for y in powerset_items:
                candida_FP.add(tuple(sorted(x | y)))
    print(f"Time 2 (CFD Mining): {time.time() - time_Start2:.4f} s")
    return candida_FP

# ----------------- Computing Support -----------------
def Computing_Support_Fast_Optimized(candida_FP, min_supp_count, items):
    time_Start3 = time.time()
    Frequent_Pattern = {}
    Frequent_Prefix = set()
    items_set = {str(item): set(tids) for item, tids in items.items()}
    sorted_patterns = sorted(candida_FP, key=lambda x: (len(x), x))
    for pattern in sorted_patterns:
        if not pattern:
            continue
        if len(pattern) > 1 and any(sub not in Frequent_Prefix for sub in combinations(pattern, len(pattern)-1)):
            continue
        if any(len(items_set[it]) < min_supp_count for it in pattern):
            continue
        tids_list = [items_set[it] for it in pattern]
        tids_list.sort(key=len)
        inter = tids_list[0].copy()
        for s in tids_list[1:]:
            inter &= s
            if len(inter) < min_supp_count:
                break
        else:
            Frequent_Pattern[tuple(pattern)] = len(inter)
            Frequent_Prefix.add(tuple(pattern))
    print(f"Time 3 (Support Counting): {time.time() - time_Start3:.4f} s")
    return Frequent_Pattern

# ----------------- Main Entry Point -----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A Dependency-Driven Framework for FIM (RQFP)")
    parser.add_argument("--dataset", type=str, default="./data/adult1.csv", help="Path to input dataset (CSV)")
    parser.add_argument("--lhs", type=int, nargs="+", default=[1, 7], help="LHS columns indexes (zero-based)")
    parser.add_argument("--rhs", type=int, nargs="+", default=[9], help="RHS columns indexes (zero-based)")
    parser.add_argument("--support", type=float, default=0.3, help="Minimum support threshold (0.0 to 1.0)")
    parser.add_argument("--band", type=int, default=500, help="Partition size boundary (band)")
    parser.add_argument("--out_dir", type=str, default="./sub-datasets", help="Directory for intermediate tables")
    parser.add_argument("--output", type=str, default="results/frequent_patterns_FW_FPG.json", help="Path to save output patterns (JSON)")
    args = parser.parse_args()

    tracemalloc.start()
    global_start = time.time()

    # Step 1: Preprocessing & Decomposition
    print(f"--- 1. Decomposing database based on FDs {args.lhs} -> {args.rhs} ---")
    R, K, items = preprocessing1(
        lhs_fd=args.lhs, 
        rhs_fd=args.rhs, 
        csv_path=args.dataset, 
        out_dir=args.out_dir, 
        band=args.band,
    )
    t1 = time.time() - global_start
    _, peak_pre = tracemalloc.get_traced_memory()
    print(f"Preprocessing Peak Memory: {peak_pre / 1024 / 1024:.2f} MB\n")

    min_count = max(1, int(R * args.support))
    print(f"Database Rows (R): {R} | Min Support Count (minsup): {min_count}\n")

    # Step 2: Candidate Generation (Local Mining)
    print("--- 2. Mining subdatasets using RQFP-Mine ---")
    tracemalloc.reset_peak()
    start_step2 = time.time()
    candida_FP = build_candidates_from_subdatasets(args.out_dir,min_count,R)
    t2 = time.time() - start_step2
    _, peak_mining = tracemalloc.get_traced_memory()
    print(f"Number of Candidates Generated: {len(candida_FP)}")
    print(f"Mining Peak Memory: {peak_mining / 1024 / 1024:.2f} MB\n")

    # Step 3: Global Support Counting
    print("--- 3. Verifying candidate support globally ---")
    tracemalloc.reset_peak()
    start_step3 = time.time()
    s = Computing_Support_Fast_Optimized(candida_FP, min_count, items)
    t3 = time.time() - start_step3
    _, peak_support = tracemalloc.get_traced_memory()
    print(f"Support Verification Peak Memory: {peak_support / 1024 / 1024:.2f} MB\n")

    # Step 4: Export Results to JSON
    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        export_data = {
            "experiment_meta": {
                "dataset": args.dataset,
                "lhs": args.lhs,
                "rhs": args.rhs,
                "support_threshold": args.support,
                "min_support_count": min_count,
                "band_parameter": args.band,
                "total_rows": R,
                "subdatasets_generated": K,
                "execution_time_sec": {
                    "decomposition": round(t1, 4),
                    "local_mining": round(t2, 4),
                    "support_counting": round(t3, 4),
                    "total": round(t1 + t2 + t3, 4)
                }
            },
            "frequent_patterns": {";".join(k): v for k, v in s.items()}
        }
        with open(args.output, "w", encoding="utf-8") as out_file:
            json.dump(export_data, out_file, indent=4, ensure_ascii=False)

    # Global Summary
    print("----------------- Execution Summary -----------------")
    print(f"Total Frequent Patterns: {len(s)}")
    print(f"Total Runtime: {t1 + t2 + t3:.4f} seconds")
    
    _, peak_total = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"Total Peak Memory Usage: {peak_total / 1024 / 1024:.2f} MB")
    if args.output:
        print(f"Frequent patterns successfully exported to: {args.output}")
    print("-----------------------------------------------------")

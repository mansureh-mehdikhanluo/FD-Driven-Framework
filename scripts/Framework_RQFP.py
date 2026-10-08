import csv
import os
import json
import time
import argparse
from collections import defaultdict, Counter
from itertools import chain, combinations
from typing import List, Tuple, Set, Dict, Any
import tracemalloc

# ----------------- Utility -----------------
def power_set(items: List[Any]) -> List[Tuple[Any, ...]]:
    """Generate powerset of a list."""
    return list(chain.from_iterable(combinations(items, r) for r in range(1, len(items)+1)))

def build_mining_table(transactions: List[List[str]], min_support: int) -> List[Tuple[Tuple[str, ...], int]]:
    """Build a compressed mining table with weights for the given transactions."""
    item_counts = Counter()
    for t in transactions:
        for item in set(t):
            item_counts[item] += 1

    frequent_items = {i for i, c in item_counts.items() if c >= min_support}
    if not frequent_items:
        return []

    L = sorted(frequent_items, key=lambda i: (-item_counts[i], str(i)))
    index_in_L = {item: idx for idx, item in enumerate(L)}

    tmp_table = []
    for t in transactions:
        filtered = [i for i in set(t) if i in frequent_items]
        if not filtered:
            continue
        filtered.sort(key=lambda i: index_in_L[i])
        tmp_table.append((tuple(filtered), 1))

    merged = defaultdict(int)
    for items, w in tmp_table:
        merged[items] += w

    return [(items, w) for items, w in merged.items()]

# ----------------- Preprocessing & Decomposition -----------------
def preprocessing1(
    lhs_fd: List[int], 
    rhs_fd: List[int], 
    csv_path: str, 
    out_dir: str, 
    band: int, 
    min_supp: float, 
    max_rows: int = None
) -> Tuple[int, int, Dict[str, List[int]]]:
    """
    Decompose the dataset into partitions based on FD and export intermediate mining tables.
    """
    start_time = time.time()
    os.makedirs(out_dir, exist_ok=True)
    
    # Remove older intermediate tables from the output directory to avoid collision
    for f in os.listdir(out_dir):
        if f.startswith("mining_table_") and f.endswith(".csv"):
            try:
                os.remove(os.path.join(out_dir, f))
            except OSError:
                pass

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
    min_count = int(total_rows * min_supp)
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

        const_set = set(constant_items)
        transactions = []
        for _, items in rows:
            filtered = [it for it in items.values() if it not in const_set]
            if filtered:
                transactions.append(filtered)

        if not transactions:
            continue

        new_min_sup = max(1, int(min_count * len(transactions) / total_rows))
        mining_table = build_mining_table(transactions, min_support=new_min_sup)
        if not mining_table:
            continue

        num_subdatasets += 1
        path = os.path.join(out_dir, f"mining_table_{num_subdatasets}.csv")
        with open(path, "w", newline="", encoding="utf-8") as out_f:
            w = csv.writer(out_f)
            w.writerow(["#META"])
            w.writerow(["num_transactions", len(transactions)])
            w.writerow(["min_support", new_min_sup])
            w.writerow(["#POWERSET"])
            for r0 in range(1, min(5, len(constant_items)) + 1):
                for ps in combinations(constant_items, r0):
                    w.writerow([json.dumps(list(ps), ensure_ascii=False)])
            w.writerow(["#MINING_TABLE"])
            for items_row, weight in mining_table:
                w.writerow([json.dumps(list(items_row), ensure_ascii=False), weight])

    if small_transactions:
        r = len(small_transactions)
        new_min_sup = max(1, int(min_count * r / total_rows))
        mining_table = build_mining_table(small_transactions, min_support=new_min_sup)
        if mining_table:
            num_subdatasets += 1
            path = os.path.join(out_dir, f"mining_table_{num_subdatasets}.csv")
            with open(path, "w", newline="", encoding="utf-8") as out_f:
                w = csv.writer(out_f)
                w.writerow(["#META"])
                w.writerow(["num_transactions", r])
                w.writerow(["min_support", new_min_sup])
                w.writerow(["#POWERSET"])
                w.writerow(["#MINING_TABLE"])
                for items_row, weight in mining_table:
                    w.writerow([json.dumps(list(items_row), ensure_ascii=False), weight])
                    
    print(f"Time 1 (Preprocessing & Decomposition): {time.time() - start_time:.4f} s")
    return total_rows, num_subdatasets, dict(item_row_index)

# ----------------- RQFP Mining Core -----------------
def rqfp_mine(mining_table: List[Tuple[Tuple[str, ...], int]], min_support: int) -> Dict[frozenset, int]:
    """Perform recursive projection mining (RQFP-Mine) on a local mining table."""
    patterns = {}
    def dfs(prefix: Tuple[str, ...], projected_db: List[Tuple[Tuple[str, ...], int]]):
        local_support: Counter = Counter()
        for items_row, w in projected_db:
            for item in items_row:
                local_support[item] += w
        local_freq_items = [i for i, c in local_support.items() if c >= min_support]
        if not local_freq_items:
            return
        local_freq_items.sort(key=lambda i: (-local_support[i], str(i)))
        for item in local_freq_items:
            new_prefix = prefix + (item,)
            patterns[frozenset(new_prefix)] = local_support[item]
            new_proj = []
            for items_row, w in projected_db:
                if item in items_row:
                    idx = items_row.index(item)
                    suffix = items_row[idx + 1:]
                    if suffix:
                        new_proj.append((suffix, w))
            if new_proj:
                dfs(new_prefix, new_proj)
    dfs((), mining_table)
    return patterns

# ----------------- Candidate Builder -----------------
def build_candidates_from_subdatasets(out_dir: str) -> Set[Tuple[str, ...]]:
    """Mine local subdatasets and assemble global frequent candidates."""
    start_time = time.time()
    candida_FP: Set[Tuple[str, ...]] = set()
    mining_files = sorted(f for f in os.listdir(out_dir) if f.startswith("mining_table_") and f.endswith(".csv"))

    for filename in mining_files:
        file_path = os.path.join(out_dir, filename)
        powerset = []
        mining_table = []
        min_support = 1

        section = None
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                cell = row[0].strip()
                if cell.startswith("#"):
                    section = cell
                    continue
                if section == "#META":
                    if row[0] == "min_support":
                        min_support = int(row[1])
                elif section == "#POWERSET":
                    powerset.append(tuple(json.loads(row[0])))
                elif section == "#MINING_TABLE":
                    items_row = tuple(json.loads(row[0]))
                    mining_table.append((items_row, int(row[1])))

        if not mining_table:
            continue
            
        patterns = rqfp_mine(mining_table, min_support)
        FP_sets = patterns.keys()
        powerset_sets = [frozenset(p) for p in powerset]
        
        for x in FP_sets:
            candida_FP.add(tuple(sorted(x)))
        for y in powerset_sets:
            candida_FP.add(tuple(sorted(y)))
        for x in FP_sets:
            for y in powerset_sets:
                candida_FP.add(tuple(sorted(x | y)))

    print(f"Time 2 (CFD local mining): {time.time() - start_time:.4f} s")
    return candida_FP

# ----------------- Computing Support (Optimized) -----------------
def Computing_Support_Fast_Optimized(
    candida_FP: Set[Tuple[str, ...]], 
    min_supp_count: int, 
    items: Dict[str, List[int]]
) -> Dict[Tuple[str, ...], int]:
    """
    Optimized support counting using tid-list intersections, early pruning 
    via prefix check, and support order heuristics.
    """
    start_time = time.time()
    Frequent_Pattern = {}
    Frequent_Prefix = set()

    items_set = {item: set(tids) for item, tids in items.items()}

    # Sort candidates: shorter lengths first, then by sum of tid-list lengths (ascending)
    sorted_patterns = sorted(
        candida_FP, 
        key=lambda x: (len(x), sum(len(items_set.get(it, [])) for it in x))
    )

    for pattern in sorted_patterns:
        if not pattern:
            continue

        # Prefix Check: Prune if any subset of size n-1 is not frequent
        if len(pattern) > 1 and any(sub not in Frequent_Prefix for sub in combinations(pattern, len(pattern)-1)):
            continue

        # Prune if any single item lacks minimum support
        if any(len(items_set.get(it, [])) < min_supp_count for it in pattern):
            continue

        # Perform fast intersection ordered by tid-list length
        try:
            tids_list = sorted((items_set[it] for it in pattern), key=len)
        except KeyError:
            continue
            
        inter = tids_list[0].copy()
        for s in tids_list[1:]:
            inter &= s
            if len(inter) < min_supp_count:
                break
        else:
            Frequent_Pattern[tuple(pattern)] = len(inter)
            Frequent_Prefix.add(tuple(pattern))

    print(f"Time 3 (Optimized Support Counting): {time.time() - start_time:.4f} s")
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
    parser.add_argument("--output", type=str, default="results/frequent_patterns_FW_RQFP.json", help="Path to save output patterns (JSON)")
    parser.add_argument("--max_rows", type=int, default=None, help="Maximum number of rows to load from the dataset")
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
        min_supp=args.support,
        max_rows=args.max_rows,
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
    candida_FP = build_candidates_from_subdatasets(args.out_dir)
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

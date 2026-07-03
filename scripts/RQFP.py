import os
import time
import csv
from collections import Counter, defaultdict
from typing import List, Tuple, Dict, FrozenSet, Optional
import tracemalloc
import json
import argparse

# ----------------- Mining Table Save/Load Utilities -----------------

def save_mining_table_csv(
    path: str,
    mining_table: List[Tuple[Tuple[str, ...], int]],
):
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Header row to describe columns
            writer.writerow(["items", "weight"])
            for items, weight in mining_table:
                writer.writerow([
                    # Serialize the tuple of items into a JSON list string
                    json.dumps(list(items), ensure_ascii=False),
                    weight
                ])
    except IOError as e:
        print(f"Error saving mining table to {path}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during saving: {e}")

def load_mining_table_csv(
    path: str,
) -> List[Tuple[Tuple[str, ...], int]]:
    mining_table: List[Tuple[Tuple[str, ...], int]] = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Verify expected header columns exist
            if "items" not in reader.fieldnames or "weight" not in reader.fieldnames:
                print(f"Error: Missing expected columns ('items', 'weight') in CSV file: {path}")
                return []
                
            for row in reader:
                try:
                    # Deserialize the JSON string back into a list, then convert to tuple
                    items = tuple(json.loads(row["items"]))
                    weight = int(row["weight"])
                    mining_table.append((items, weight))
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    print(f"Warning: Skipping row due to parsing error in {path}: {row}. Error: {e}")
    except FileNotFoundError:
        print(f"Error: Mining table file not found at {path}.")
    except IOError as e:
        print(f"Error loading mining table from {path}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during loading: {e}")
        
    return mining_table

# ----------------- Mining Table Builder Utility -----------------

def build_mining_table(
    transactions: List[List[str]],
    min_support: int,
) -> Tuple[List[Tuple[Tuple[str, ...], int]], List[str], Dict[str, int]]:
    # Count frequencies of all items across all transactions
    item_counts: Counter[str] = Counter()
    for t in transactions:
        # Use set(t) to count each item only once per transaction for support calculation
        item_counts.update(set(t))

    # Identify items that meet the minimum support threshold
    frequent_items = {i for i, c in item_counts.items() if c >= min_support}
    
    # If no items meet the threshold, return empty results
    if not frequent_items:
        return [], [], dict(item_counts)

    # Sort frequent items: primary key frequency (desc), secondary key item name (asc)
    # This order is often used in mining algorithms for consistency
    L = sorted(frequent_items, key=lambda i: (-item_counts[i], str(i)))
    # Create a mapping from item to its index in the sorted list L for efficient lookup
    index_in_L = {item: idx for idx, item in enumerate(L)}

    # Create a temporary list of transactions filtered by frequent items and sorted
    tmp_table_entries: List[Tuple[Tuple[str, ...], int]] = []
    for t in transactions:
        # Filter the transaction to include only frequent items
        filtered_items_in_t = [i for i in set(t) if i in frequent_items]
        if not filtered_items_in_t:
            continue # Skip if no frequent items are in this transaction

        # Sort the filtered items according to the global order L
        filtered_items_in_t.sort(key=lambda i: index_in_L[i])
        # Append the sorted tuple of items and a weight of 1 (representing one occurrence)
        tmp_table_entries.append((tuple(filtered_items_in_t), 1))

    # Aggregate weights for identical itemsets
    # defaultdict(int) initializes new keys with a value of 0
    merged_itemsets: Dict[Tuple[str, ...], int] = defaultdict(int)
    for items_tuple, weight in tmp_table_entries:
        merged_itemsets[items_tuple] += weight

    # Convert the merged dictionary into the final mining table format
    mining_table = list(merged_itemsets.items())
    
    return mining_table, L, dict(item_counts)

# ----------------- RQFP Mining Algorithm -----------------

def rqfp_mine(
    mining_table: List[Tuple[Tuple[str, ...], int]],
    min_support: int,
) -> Dict[FrozenSet[str], int]:
    # Dictionary to store the final frequent patterns found
    patterns: Dict[FrozenSet[str], int] = {}

    def dfs(prefix: Tuple[str, ...], projected_db: List[Tuple[Tuple[str, ...], int]]):
        # Count the frequency of each item within the current projected database
        local_support: Counter[str] = Counter()
        for items, w in projected_db:
            for item in items:
                local_support[item] += w

        # Identify items that meet the minimum support threshold in this projection
        local_freq_items = [i for i, c in local_support.items() if c >= min_support]
        
        # If no local frequent items are found, backtrack
        if not local_freq_items:
            return

        # Sort locally frequent items by frequency (desc) then name (asc)
        local_freq_items.sort(key=lambda i: (-local_support[i], str(i)))

        # Explore each locally frequent item
        for item in local_freq_items:
            # Extend the current prefix with the new item
            new_prefix = prefix + (item,)
            # Record the pattern and its support count
            patterns[frozenset(new_prefix)] = local_support[item]

            # Construct the new projected database for the next recursive call
            new_proj: List[Tuple[Tuple[str, ...], int]] = []
            for items, w in projected_db:
                # Check if the current item exists in the itemset
                if item in items:
                    # Find the index of the item to extract the suffix
                    try:
                        idx = items.index(item)
                        # The suffix contains items appearing *after* the current item
                        suffix = items[idx + 1:]
                        # If the suffix is not empty, add it to the new projection
                        if suffix:
                            new_proj.append((suffix, w))
                    except ValueError:
                        # Should not happen if 'item in items' is true, but good practice
                        continue 

            # If the new projected database is not empty, recurse
            if new_proj:
                dfs(new_prefix, new_proj)

    # Start the DFS process with an empty prefix and the initial mining table
    dfs((), mining_table)
    return patterns

# ----------------- CSV Transaction Loader -----------------

def load_transactions_from_csv(
    path: str, 
    max_rows: Optional[int] = None
) -> List[List[str]]:
    transactions: List[List[str]] = []
    try:
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            # This simple loader assumes DictReader works directly on the raw data file
            
            for idx, row in enumerate(reader):
                if max_rows is not None and idx >= max_rows:
                    break
                
                # Extract items from the row, filtering out empty, '?', or whitespace-only values
                items = [
                    f"{col.strip()}={val.strip()}"
                    for col, val in row.items()
                    if val and val.strip() != "?" and val.strip() != ""
                ]
                
                if items: # Only add if the transaction has at least one valid item
                    transactions.append(items)
                    
    except FileNotFoundError:
        print(f"Error: Transaction file not found at {path}.")
    except IOError as e:
        print(f"Error reading transaction file {path}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while loading transactions: {e}")
        
    return transactions

# ===========================
# Main Execution Block
# ===========================
if __name__ == "__main__":
    # --- Configuration ---
    CSV_PATH = "adult1.csv" # Default dataset path
    ENABLE_DETAILED_LOGGING = False # Set to True for more console output during execution

    parser = argparse.ArgumentParser(description="A Dependency-Driven Framework for FIM (RQFP)")
    parser.add_argument("--dataset", type=str, default="./data/adult1.csv", help="Path to input dataset (CSV)")
    parser.add_argument("--support", type=float, default=0.3, help="Minimum support threshold (0.0 to 1.0)")
    parser.add_argument("--output", type=str, default="output/Mining_Table.csv", help="Path to save output patterns (JSON)")
    parser.add_argument("--result", type=str, default="results/frequent_patterns_RQFP.json", help="Path to save output patterns (JSON)")
    parser.add_argument("--max_rows", type=str, default=None, help="Maximum size og data")
    args = parser.parse_args()

    # --- Initialize Tracemalloc for memory profiling ---
    tracemalloc.start()
    start_total_time = time.time()
    
    # --- Step 1: Load Transactions ---
    print("--- Step 1: Loading Transactions ---")
    tracemalloc.reset_peak() # Reset peak memory counter before this step
    load_start_time = time.time()

    transactions = load_transactions_from_csv(args.dataset, args.max_rows)
    num_transactions = len(transactions)

    load_time = round(time.time() - load_start_time, 3)
    current_mem, peak_mem_load = tracemalloc.get_traced_memory()
    peak_mem_load_mb = peak_mem_load / (1024 * 1024)

    print(f"Loaded {num_transactions} transactions in {load_time}s")
    print(f"Peak Memory Usage (Loading): {peak_mem_load_mb:.2f} MB")

    if num_transactions == 0:
        print("No transactions loaded. Exiting.")
        exit()

    # --- Step 2: Calculate Minimum Support Count ---
    # Ensure minimum support count is at least 1
    min_support_count = max(1, int(num_transactions * args.support))
    print(f"\nCalculated minimum support count: {min_support_count} (for {args.support*100}%)")

    # --- Step 3: Build and Save Mining Table ---
    print("\n--- Step 3: Building and Saving Mining Table ---")
    tracemalloc.reset_peak() # Reset peak memory counter
    build_start_time = time.time()

    mining_table, L_frequent_items, all_item_counts = build_mining_table(
        transactions, 
        min_support_count
    )
    
    # Save the built mining table to CSV
    save_mining_table_csv(args.output, mining_table)

    build_time = round(time.time() - build_start_time, 3)
    current_mem, peak_mem_build = tracemalloc.get_traced_memory()
    peak_mem_build_mb = peak_mem_build / (1024 * 1024)

    print(f"Built and saved mining table ({len(mining_table)} entries) in {build_time}s")
    print(f"Mining Table Construction Peak Memory: {peak_mem_build_mb:.2f} MB")
    if ENABLE_DETAILED_LOGGING:
         print(f"Frequent items (L): {L_frequent_items}")

    # --- Step 4: Load Mining Table from CSV ---
    # This simulates loading the intermediate table, useful for testing RQFP independently
    print("\n--- Step 4: Loading Mining Table from CSV ---")
    tracemalloc.reset_peak() # Reset peak memory counter
    load_table_start_time = time.time()

    mining_table_loaded = load_mining_table_csv(args.output)

    load_table_time = round(time.time() - load_table_start_time, 3)
    current_mem, peak_mem_load_table = tracemalloc.get_traced_memory()
    peak_mem_load_table_mb = peak_mem_load_table / (1024 * 1024)

    print(f"Loaded mining table ({len(mining_table_loaded)} entries) in {load_table_time}s")
    print(f"Mining Table Loading Peak Memory: {peak_mem_load_table_mb:.2f} MB")

    if not mining_table_loaded:
        print("Failed to load mining table. Exiting.")
        exit()

    # --- Step 5: Run RQFP Mining Algorithm ---
    print("\n--- Step 5: Running RQFP Mining ---")
    tracemalloc.reset_peak() # Reset peak memory counter
    rqfp_start_time = time.time()

    frequent_patterns_dict = rqfp_mine(mining_table_loaded, min_support_count)

    rqfp_time = round(time.time() - rqfp_start_time, 3)
    current_mem, peak_mem_rqfp = tracemalloc.get_traced_memory()
    peak_mem_rqfp_mb = peak_mem_rqfp / (1024 * 1024)

    print(f"RQFP mining completed. Found {len(frequent_patterns_dict)} patterns in {rqfp_time}s")
    print(f"RQFP Mining Peak Memory: {peak_mem_rqfp_mb:.2f} MB")

    # --- Step 6: Save Frequent Patterns to JSON ---
    print(f"\n--- Step 6: Saving Frequent Patterns to {args.result} ---")
    save_patterns_start_time = time.time()

    if args.result:
        os.makedirs(os.path.dirname(args.result), exist_ok=True)
        # Prepare data for JSON export
        # Convert frozensets to sorted lists for JSON compatibility
        export_patterns = {
            ";".join(sorted(list(p))): count
            for p, count in frequent_patterns_dict.items()
        }
        
        export_data = {
            "metadata": {
                "dataset": args.dataset,
                "min_support_percentage": args.support,
                "min_support_count": min_support_count,
                "total_transactions_processed": num_transactions,
                "mining_table_entries": len(mining_table),
                "execution_times_sec": {
                    "loading_transactions": load_time,
                    "building_mining_table": build_time,
                    "loading_mining_table": load_table_time,
                    "rqfp_mining": rqfp_time,
                    "saving_patterns": None # Will be calculated below
                },
                "peak_memory_mb": {
                     "loading": peak_mem_load_mb,
                     "building_table": peak_mem_build_mb,
                     "loading_table": peak_mem_load_table_mb,
                     "rqfp_mining": peak_mem_rqfp_mb,
                     "total_peak": None # Will be calculated below
                }
            },
            "frequent_patterns": export_patterns
        }

        try:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=4, ensure_ascii=False)
            save_patterns_time = round(time.time() - save_patterns_start_time, 3)
            export_data["metadata"]["execution_times_sec"]["saving_patterns"] = save_patterns_time
            print(f"Successfully saved frequent patterns in {save_patterns_time}s")
        except IOError as e:
            print(f"Error saving frequent patterns to {args.results}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during saving patterns: {e}")

    # --- Final Summary ---
    total_execution_time = round(time.time() - start_total_time, 3)
    current_mem, peak_total_mem = tracemalloc.get_traced_memory() # Get final memory usage
    tracemalloc.stop()
    peak_total_mem_mb = peak_total_mem / (1024 * 1024)
    
    # Update total peak memory in metadata
    if args.result and 'metadata' in export_data:
        export_data["metadata"]["peak_memory_mb"]["total_peak"] = peak_total_mem_mb

    print("\n--- Overall Execution Summary ---")
    print(f"Total Runtime: {total_execution_time}s")
    print(f"Total Peak Memory Usage: {peak_total_mem_mb:.2f} MB")
    print(f"Number of frequent patterns found by RQFP: {len(frequent_patterns_dict)}")
    if args.result:
        print(f"Frequent patterns saved to: {args.result}")
    print("---------------------------------")

    # Update the metadata with final calculated values if JSON was saved
    if args.result and 'metadata' in export_data:
        export_data["metadata"]["total_execution_time_sec"] = total_execution_time
        try:
             with open(args.result, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
             print(f"Could not update JSON with final summary: {e}")

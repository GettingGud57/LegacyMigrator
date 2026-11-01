import pyarrow.parquet as pq

def load(path):
    return pq.read_table(path).to_pylist()


def index_by_key(rows, key_cols):
    index ={}
    dupes =[]
    for row in rows:
        key = tuple(row[col] for col in key_cols)
        if key in index:
            dupes.append(key)
        else:
            index[key] = row
    
    
    return {
        "index":index,
        "dupes":dupes
    }


def diff(rows_a, rows_b, key_cols, ignore_cols=()):
    a_result = index_by_key(rows_a, key_cols)
    a_index = a_result["index"]
    b_result = index_by_key(rows_b, key_cols)
    b_index = b_result["index"]
    
    a_cols = rows_a[0].keys() if rows_a else set()
    b_cols = rows_b[0].keys() if rows_b else set()
    
    cols_only_a = a_cols - b_cols
    cols_only_b = b_cols - a_cols
    
    
    
    rows_only_a = set(a_index.keys()) - set(b_index.keys())
    rows_only_b = set(b_index.keys()) - set(a_index.keys())     
    changed =[]
    intersect = set(a_index.keys()) & set(b_index.keys())
    for key in intersect:
        a_row = a_index[key]
        b_row = b_index[key]
        for col in a_row.keys():
            if col in ignore_cols:
                continue
            if a_row[col] != b_row[col]:
                changed.append({
                    "key":key,
                    "col":col,
                    "a":a_row[col],
                    "b":b_row[col]
                })
        
         
    

    return {
        "cols_only_a": list(cols_only_a),
        "cols_only_b": list(cols_only_b),
        "rows_only_a": list(rows_only_a),
        "rows_only_b": list(rows_only_b),
        "changed": changed,
        "dupes_a": a_result["dupes"],
        "dupes_b": b_result["dupes"],
    }


def show(title, items, limit):
    """Print a titled list, at most `limit` items. Prints nothing if the list is empty."""
    items = sorted(items, key=str)  # sorted as text, so None or mixed types can't crash it
    if not items:
        return
    print(f"{title} ({len(items)}):")
    for item in items[:limit]:
        print(f"  {item}")
    if len(items) > limit:
        print(f"  ... and {len(items) - limit} more")


def report(result, limit=10):
    changed = result["changed"]
    rows_changed = len({c["key"] for c in changed})

    # 1. Summary line: the counts that matter most
    print(f"rows only in A: {len(result['rows_only_a'])}   "
          f"rows only in B: {len(result['rows_only_b'])}   "
          f"rows changed: {rows_changed}   "
          f"cells changed: {len(changed)}")

    # 2. Findings: which rows, and which cells
    show("only in A", result["rows_only_a"], limit)
    show("only in B", result["rows_only_b"], limit)
    if changed:
        print(f"first {min(limit, len(changed))} changes:")
        for c in sorted(changed, key=lambda c: (str(c["key"]), c["col"]))[:limit]:
            print(f"  {c['key']}  {c['col']}  {c['a']!r} -> {c['b']!r}")

    # 3. Warnings: things the comparison couldn't check
    show("WARNING duplicate keys in A", result["dupes_a"], limit)
    show("WARNING duplicate keys in B", result["dupes_b"], limit)
    show("WARNING columns only in A", result["cols_only_a"], limit)
    show("WARNING columns only in B", result["cols_only_b"], limit)


if __name__ == "__main__":
    # Warm-up: the worked example from the question
    a = [
        {"id": 1, "name": "Anna", "city": "Cork"},
        {"id": 2, "name": "Ben",  "city": "Cork"},
        {"id": 3, "name": "Cara", "city": "Galway"},
    ]
    b = [
        {"id": 4, "name": "Dan",  "city": "Sligo"},
        {"id": 1, "name": "Anna", "city": "Dublin"},
        {"id": 2, "name": "Ben",  "city": "Cork"},
    ]
    print("=== worked example ===")
    report(diff(a, b, ["id"]))

    # Real test: what the legacy sales job changed in staging
    
    
    print("\n=== Sale_Staging: before vs after ===")
    rows_a = load("snapshots/sale/before/Integration.Sale_Staging.parquet")
    rows_b = load("snapshots/sale/after/Integration.Sale_Staging.parquet")
    report(diff(rows_a, rows_b, key_cols=["Sale Staging Key"]))
    
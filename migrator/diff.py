import pyarrow.parquet as pq
from collections import Counter

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
    
    
def compare_rows(rows_a, rows_b, cols):
    a_rows = [tuple(row[col] for col in cols) for row in rows_a]
    b_rows = [tuple(row[col] for col in cols) for row in rows_b]
    a_count = Counter(a_rows)
    b_count = Counter(b_rows)
    return {
        "only_a": list((a_count - b_count).elements()),
        "only_b": list((b_count - a_count).elements()),
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
        for col in  (a_cols & b_cols)-set(ignore_cols):
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


def reconcile(rows_a, rows_b, key_cols=None, ignore_cols=()):
    """compare_rows decides PASS/FAIL. diff only explains a FAIL."""
    ignore = set(ignore_cols)
    a_cols = set(rows_a[0]) if rows_a else set()
    b_cols = set(rows_b[0]) if rows_b else set()
    cols = sorted((a_cols & b_cols) - ignore)            # same column order for A and B
    result = compare_rows(rows_a, rows_b, cols)          # whole rows with no exact match
    result["cols_only_a"] = sorted(a_cols - b_cols - ignore)
    result["cols_only_b"] = sorted(b_cols - a_cols - ignore)
    passed = not any(result.values())                    # PASS only if all four lists are empty
    result.update(status="pass" if passed else "fail", compared_cols=cols, explanation=None)
    if not passed and key_cols:
        ex = diff(rows_a, rows_b, key_cols, ignore_cols)
        dupes = set(ex["dupes_a"] + ex["dupes_b"])       # changes on duplicate keys are guesses
        ex["changed"] = [c for c in ex["changed"] if c["key"] not in dupes]
        result["explanation"] = ex
    return result


def print_verdict(result, limit=10):
    print(result["status"].upper())
    print(f"  identical-twin check: {len(result['only_a'])} rows in A and "
          f"{len(result['only_b'])} in B have no identical twin "
          f"({len(result['compared_cols'])} columns compared)")
    

    ex = result["explanation"]
    if ex:
        print("  details, pairing rows by key:")
        report(ex, limit)
    if result["status"] == "fail" and (not ex or ex["dupes_a"] or ex["dupes_b"]):
        show("whole rows only in A", result["only_a"], limit)
        show("whole rows only in B", result["only_b"], limit)
        show("WARNING columns only in A", result["cols_only_a"], limit)
        show("WARNING columns only in B", result["cols_only_b"], limit)
        



if __name__ == "__main__":
    a = [{"id": 1, "name": "Anna", "city": "Cork"},
         {"id": 2, "name": "Ben",  "city": "Cork"},
         {"id": 3, "name": "Cara", "city": "Galway"}]
    b = [{"id": 4, "name": "Dan",  "city": "Sligo"},
         {"id": 1, "name": "Anna", "city": "Dublin"},
         {"id": 2, "name": "Ben",  "city": "Cork"}]
    print("=== worked example ===")
    print_verdict(reconcile(a, b, ["id"]))

    print("\n=== duplicate key ===")
    print_verdict(reconcile([{"id": 5, "city": "Cork"}, {"id": 5, "city": "Galway"}],
                            [{"id": 5, "city": "Galway"}], ["id"]))

    staging = "Integration.Sale_Staging.parquet"
    before = load(f"snapshots/sale/before/{staging}")

    print("\n=== Sale_Staging: before vs after (the old job's changes) ===")
    print_verdict(reconcile(before, load(f"snapshots/sale/after/{staging}"), ["Sale Staging Key"]))

    print("\n=== Sale_Staging: before vs spark (noop round trip) ===")
    print_verdict(reconcile(before, load(f"snapshots/sale/spark/{staging}"), ["Sale Staging Key"]))
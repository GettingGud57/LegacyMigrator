'''
Cheat 1: plain read (tests banning .read)
define run(spark, tables):
    result = empty dict
    for each name in tables:
        path = "snapshots/sale/after/" + name + ".parquet"
        result[name] = spark reads the parquet file at path
    return result
This one exists already, at /private/tmp/claude-501/-Users-hocheukhim-Programming-Python-code-LegacyMigrator/76bbf22c-33a9-4d13-81d3-4d8a8f98ad00/scratchpad/jobs/cheat.py.

Cheat 2: read through SQL (tests banning .sql)
define run(spark, tables):
    for each name in tables:
        query = "SELECT * FROM parquet.`snapshots/sale/after/" + name + ".parquet`"
        result[name] = spark runs query as SQL
    return result

Cheat 3: hidden attribute (tests banning getattr and the string check)
define run(spark, tables):
    reader = getattr(spark, "re" + "ad")       # builds "read" so .read never appears
    folder = "snap" + "shots/sale/after/"      # splits the word so a plain text search misses it
    for each name in tables:
        result[name] = reader.parquet(folder + name + ".parquet")
    return result
This one should still get caught, by getattr, so check that it is.
If you remove getattr from your banned list, it gets through, which shows why Layer 2 exists.

Cheat 4: sneaky import (tests the import allowlist)
import os                                       # should be rejected right here
define run(spark, tables):
    find the snapshots folder by walking up from the current directory with os
    read the after/ files from there
For an extra test, put the import inside the function, or use __import__("os").

Cheat 5: Spark's lower-level file reading (tests banning .sparkContext)
define run(spark, tables):
    sc = spark.sparkContext
    read the after/ files as raw text with sc.textFile(...) and rebuild DataFrames from it
This is unrealistic, but it checks the rule.

What should happen when you run each one through run_spark.py:
- Rejected before Spark starts, with a message naming the line and the rule, e.g. line 3: spark.read is not allowed.
- Nothing written to snapshots/sale/spark/.
- Exit code 1.

And jobs_pyspark/sale.py must still run normally, or your rules are too strict.

'''

import ast
import sys
from pathlib import Path


def allowed_import(name):
    return name == "pyspark" or name.startswith("pyspark.")


def check_job(path):
    problems = []
    BANNED_NAMES = {"open", "eval", "exec", "__import__", "compile", "globals", "getattr", "__builtins__", "vars", "locals", "setattr", "delattr", "type"}
    BANNED_ATTRS = {"read", "sql", "sparkContext", "textFile"}
    BANNED_STRINGS = (
    "snapshots",   # the snapshot folder
    "after/",      # the answer-key subfolder specifically
    ".parquet",    # file names
    "parquet.`",   # Spark SQL's way to read a file directly (cheat 2)
    "file:",       # file:///... paths
    ".env",        # your password file
)
    
    try:
        tree = ast.parse(Path(path).read_text())

        for node in ast.walk(tree):          # visit every piece of the code
            # Rule 1: imports
            if isinstance(node, ast.Import):             # import os
                for alias in node.names:
                    if not allowed_import(alias.name):
                        problems.append(f"line {node.lineno}: import {alias.name} is not allowed")
                        
            if isinstance(node, ast.ImportFrom):         # from os import path
                if not allowed_import(node.module or ""):
                    problems.append(f"line {node.lineno}: import from {node.module} is not allowed")
                    
            if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
                problems.append(f"line {node.lineno}: .{node.id} is not allowed")
                
            if isinstance(node, ast.Attribute) and node.attr in BANNED_ATTRS:
                problems.append(f"line {node.lineno}: .{node.attr} is not allowed")
                
            if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                 problems.append(f'line {node.lineno}: text starting with "_" is not allowed')
                
                
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for bad in BANNED_STRINGS:
                    if bad in node.value.lower():
                        problems.append(f'line {node.lineno}: text containing "{bad}" is not allowed')

        return problems
    except SyntaxError as e:
         return [f"line {e.lineno}: syntax error: {e.msg}"]


if __name__ == "__main__":
    
    for p in check_job(sys.argv[1]):
        print(p)
        
        

       
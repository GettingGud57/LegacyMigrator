import subprocess, sys
from pathlib import Path
import pyarrow.parquet as pq

CONTRACT = """You are translating a legacy SQL Server stored procedure into PySpark.

Write one Python file that defines exactly this function:

    def run(spark, tables):
        ...
        return {...}

Inputs:
- `spark` is an already-running SparkSession. Don't create or stop one.
- `tables` is a dict mapping table name -> DataFrame. The names and columns are
  listed below. These are the tables exactly as they were before the procedure ran.

Output:
- Return a dict mapping table name -> DataFrame, containing ONLY the tables the
  procedure changes. Tables you don't return are kept as they were.
- Each returned DataFrame is the WHOLE table after the procedure ran, not just the
  changed rows. It replaces the old table completely.
- Keep the exact same column names as the input table. Don't add or drop columns.

Rules:
- Spark has no UPDATE, DELETE or MERGE on these DataFrames. Rebuild the table instead:
  e.g. an UPDATE becomes a join/select that produces every row with the new values;
  a DELETE becomes a filter or anti-join.
- Column names contain spaces. Use F.col("Customer Key") or backticks in Spark SQL.
- A column listed with type `null` is empty in the input, so its real type is unknown
  from the data. Work out the right type froasm the SQL and cast to it when you fill it.
- Match SQL Server semantics: NULLs in joins and comparisons, integer division,
  decimal precision, string trimming.
- Only use pyspark (e.g. `from pyspark.sql import functions as F`). No other libraries,
  no reading or writing files, no database connections, no printing.
"""

def describe_tables(job):
    # For every Parquet file in snapshots/<job>/before/:
    #     read only its schema with pq.read_schema(path), not the data
    #     make one line: the table name, then each column and its type
    # Give back all the lines as one string.
    lines = []
    for f in sorted((Path("snapshots") / job / "before").glob("*.parquet")):
        schema = pq.read_schema(f)
        parts = [f"{field.name} {field.type}" for field in schema]
        lines.append(f.stem + ": " + ", ".join(parts))
    return "\n".join(lines)


def build_prompt(sql_text, tables_text):
    # Glue together: CONTRACT, the table descriptions, and the legacy SQL.
    # End with: "Reply with exactly one ```python code block and nothing else.
    #           Don't create or edit any files."
    return (
        CONTRACT
        + "\n\nTables (name: column type, ...):\n" + tables_text
        + "\n\nLegacy SQL to translate:\n" + sql_text
        + "\n\nReply with exactly one ```python code block and nothing else. "
          "Don't create or edit any files."
    )
       
def ask_claude(prompt):
    # Run the command `claude -p <prompt>` with subprocess, wait for it,
    # and give back what it printed.
    # If it fails, stop and show the error.
    result=subprocess.run(
        ["claude","-p",prompt],
        capture_output= True,
        text= True
    )
    if result.returncode != 0:
        sys.exit(f"claude failed (exit code {result.returncode}):\n"
                 f"stderr: {result.stderr}\nstdout: {result.stdout}")
   
    
    return result.stdout

def extract_code(answer):
    # Find the ```python ... ``` block in the answer and give back what's inside.
    # If there isn't exactly one, stop with a clear message.
    block = answer.count("```python")
    if(block != 1):
          sys.exit(f"Expected exactly one ```python block, found {block}:\n{answer}")
    start = answer.find("```python")+10
    end = answer.find("```", start)
    if end == -1:
        sys.exit("python block never closed:\n" + answer)
          
    return answer[start:end]
        
    


if __name__ == "__main__":
    # Read the job name and SQL file path from the command line.
    # describe → build prompt → ask → extract
    # Save it to jobs_pyspark/<job>.py and print where it went.
    if len(sys.argv) != 3:
        sys.exit("Usage: python migrator/translate.py <job> path/to/job.sql")
    job = sys.argv[1]
    sql_path = Path(sys.argv[2])

    tables_text = describe_tables(job)
    if not tables_text:
        sys.exit(f"No snapshots in snapshots/{job}/before/. Run: python migrator/run_legacy.py {job}")
    sql_text = sql_path.read_text()

    prompt = build_prompt(sql_text, tables_text)
    answer = ask_claude(prompt)
    code = extract_code(answer)

    out_path = Path("jobs_pyspark") / f"{job}.py"
    out_path.write_text(code)
    print(f"Saved to {out_path}")
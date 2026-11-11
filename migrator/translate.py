import argparse
import sys
from pathlib import Path

import anthropic
import pyarrow.parquet as pq
from dotenv import load_dotenv

DEFAULT_MODEL = "claude-sonnet-5-5"
# USD per million tokens (input, output), for the cost line printed after each call
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

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
  from the data. Work out the right type from the SQL and cast to it when you fill it.
- Match SQL Server semantics: NULLs in joins and comparisons, integer division,
  decimal precision, string trimming.
- Only use pyspark (e.g. `from pyspark.sql import functions as F`). No other libraries,
  no reading or writing files, no database connections, no printing.
- The `tables` argument is the ONLY data you may use. Compute every output from it.
  Don't use spark.read, spark.sql, spark.sparkContext, file paths, getattr, eval or exec.
  Your code is checked automatically before it runs, and code using any of these is
  rejected without running.
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
        + "\n\nReply with exactly one ```python code block and nothing else."
    )


def ask_claude(prompt, model=DEFAULT_MODEL):
    # One plain API call: text in, text out. The model gets no tools, so it
    # can't read files (snapshots, holdout) or run anything while translating.
    # Prints token usage and cost to stderr, gives back the reply text.
    load_dotenv()  # ANTHROPIC_API_KEY lives in .env
    client = anthropic.Anthropic()
    try:
        # Streaming, because a long translation can outlast a plain request's timeout
        with client.beta.messages.stream(
            model=model,
            max_tokens=64000,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            # If the model declines, the API reruns the request on Anthropic's
            # recommended fallback model. response.model says who answered.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            response = stream.get_final_message()
    except anthropic.AuthenticationError:
        sys.exit("API key rejected. Put ANTHROPIC_API_KEY=... in .env")
    except anthropic.APIStatusError as e:
        sys.exit(f"API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        sys.exit("Can't reach the Anthropic API. Check the internet connection.")

    usage = response.usage
    if response.model in PRICES:  # a fallback model may not be in the table
        price_in, price_out = PRICES[response.model]
        cost = f"${(usage.input_tokens * price_in + usage.output_tokens * price_out) / 1e6:.4f}"
    else:
        cost = "cost unknown"
    # output_tokens includes thinking, which is billed as output
    print(f"{response.model}: {usage.input_tokens} in, {usage.output_tokens} out, "
          f"{cost}, request {response._request_id}", file=sys.stderr)

    if response.stop_reason == "refusal":
        sys.exit(f"Model declined to answer: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        sys.exit("Reply was cut off at max_tokens, so the code is incomplete.")

    return "".join(block.text for block in response.content if block.type == "text")

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
    parser = argparse.ArgumentParser(description="Translate a legacy SQL job to PySpark.")
    parser.add_argument("job", help="job name, e.g. sale (reads snapshots/<job>/before/)")
    parser.add_argument("sql_path", type=Path, help="path to the legacy .sql file")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(PRICES),
                        help=f"Claude model to translate with (default {DEFAULT_MODEL})")
    args = parser.parse_args()
    job, sql_path = args.job, args.sql_path

    tables_text = describe_tables(job)
    if not tables_text:
        sys.exit(f"No snapshots in snapshots/{job}/before/. Run: python migrator/run_legacy.py {job}")
    sql_text = sql_path.read_text()

    prompt = build_prompt(sql_text, tables_text)
    answer = ask_claude(prompt, args.model)
    code = extract_code(answer)

    out_path = Path("jobs_pyspark") / f"{job}.py"
    out_path.write_text(code)
    print(f"Saved to {out_path}")
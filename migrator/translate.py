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
# Models with a server-side refusal fallback. Claude Haiku 5.5 has none, so it doesn't get
# the parameter: there a declined request simply stays declined.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}

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
- Keep the exact same column names and types as the input table. Don't add or drop
  columns. Cast every value you compute to its column's input type, e.g.
  .cast(df.schema["Column"].dataType). Timestamps in the input have no time zone.
  The one exception is a column of type `null`, described under Rules.

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


class TranslationError(Exception):
    """The translation could not be produced (API error, refusal, no code block, ...)."""


def build_prompt(sql_text, tables_text, feedback=None):
    # Glue together: CONTRACT, the table descriptions, and the legacy SQL.
    # On a retry, `feedback` says what went wrong with the previous attempt.
    # End with: "Reply with exactly one ```python code block and nothing else."
    prompt = (
        CONTRACT
        + "\n\nTables (name: column type, ...):\n" + tables_text
        + "\n\nLegacy SQL to translate:\n" + sql_text
    )
    if feedback:
        prompt += (
            "\n\nA previous translation was run and checked against the real output of the"
            " legacy procedure. It did not match. Fix it, keeping everything that was"
            " already right, and still reproduce the legacy behaviour exactly.\n\n" + feedback
        )
    return prompt + "\n\nReply with exactly one ```python code block and nothing else."


def ask_claude(prompt, model=DEFAULT_MODEL):
    # One plain API call: text in, text out. The model gets no tools, so it
    # can't read files (snapshots, holdout) or run anything while translating.
    # Prints token usage and cost to stderr, gives back the reply text.
    load_dotenv()  # ANTHROPIC_API_KEY lives in .env
    client = anthropic.Anthropic()
    fallback = {}
    if model in FALLBACK_MODELS:
        # If the model declines, the API reruns the request on Anthropic's
        # recommended fallback model. response.model says who answered.
        fallback = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    try:
        # Streaming, because a long translation can outlast a plain request's timeout
        with client.beta.messages.stream(
            model=model,
            max_tokens=64000,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            messages=[{"role": "user", "content": prompt}],
            **fallback,
        ) as stream:
            response = stream.get_final_message()
            # A streamed message has no _request_id; the stream carries it instead
            request_id = stream.request_id
    except anthropic.AuthenticationError as e:
        raise TranslationError("API key rejected. Put ANTHROPIC_API_KEY=... in .env") from e
    except anthropic.APIStatusError as e:
        raise TranslationError(f"API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise TranslationError("Can't reach the Anthropic API. Check the internet connection.") from e

    usage = response.usage
    if response.model in PRICES:  # a fallback model may not be in the table
        price_in, price_out = PRICES[response.model]
        cost = f"${(usage.input_tokens * price_in + usage.output_tokens * price_out) / 1e6:.4f}"
    else:
        cost = "cost unknown"
    # output_tokens includes thinking, which is billed as output
    print(f"{response.model}: {usage.input_tokens} in, {usage.output_tokens} out, "
          f"{cost}, request {request_id}", file=sys.stderr)

    if response.stop_reason == "refusal":
        raise TranslationError(f"Model declined to answer: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise TranslationError("Reply was cut off at max_tokens, so the code is incomplete.")

    return "".join(block.text for block in response.content if block.type == "text")


def extract_code(answer):
    # Find the ```python ... ``` block in the answer and give back what's inside.
    # If there isn't exactly one, stop with a clear message.
    blocks = answer.count("```python")
    if blocks != 1:
        raise TranslationError(f"Expected exactly one ```python block, found {blocks}:\n{answer}")
    start = answer.find("```python") + len("```python")
    end = answer.find("```", start)
    if end == -1:
        raise TranslationError("python block never closed:\n" + answer)
    return answer[start:end].strip() + "\n"


def translate(job, sql_path, model=DEFAULT_MODEL, feedback=None):
    """describe -> build prompt -> ask -> extract. Gives back the PySpark code as text."""
    tables_text = describe_tables(job)
    if not tables_text:
        raise TranslationError(
            f"No snapshots in snapshots/{job}/before/. Run: python migrator/run_legacy.py {job}")
    prompt = build_prompt(Path(sql_path).read_text(), tables_text, feedback)
    return extract_code(ask_claude(prompt, model))


if __name__ == "__main__":
    # Read the job name and SQL file path from the command line,
    # translate, save it to jobs_pyspark/<job>.py and print where it went.
    parser = argparse.ArgumentParser(description="Translate a legacy SQL job to PySpark.")
    parser.add_argument("job", help="job name, e.g. sale (reads snapshots/<job>/before/)")
    parser.add_argument("sql_path", type=Path, help="path to the legacy .sql file")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(PRICES),
                        help=f"Claude model to translate with (default {DEFAULT_MODEL})")
    args = parser.parse_args()

    try:
        code = translate(args.job, args.sql_path, args.model)
    except TranslationError as e:
        sys.exit(str(e))

    out_path = Path("jobs_pyspark") / f"{args.job}.py"
    out_path.write_text(code)
    print(f"Saved to {out_path}")

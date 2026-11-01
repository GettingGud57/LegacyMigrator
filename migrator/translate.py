import subprocess, sys
from pathlib import Path
import pyarrow.parquet as pq

CONTRACT = """(the rules below)"""

def describe_tables(job):
    # For every Parquet file in snapshots/<job>/before/:
    #     read only its schema with pq.read_schema(path), not the data
    #     make one line: the table name, then each column and its type
    # Give back all the lines as one string.


def build_prompt(sql_text, tables_text):
    # Glue together: CONTRACT, the table descriptions, and the legacy SQL.
    # End with: "Reply with exactly one ```python code block and nothing else.
    #           Don't create or edit any files."

def ask_claude(prompt):
    # Run the command `claude -p <prompt>` with subprocess, wait for it,
    # and give back what it printed.
    # If it fails, stop and show the error.

def extract_code(answer):
    # Find the ```python ... ``` block in the answer and give back what's inside.
    # If there isn't exactly one, stop with a clear message.

if __name__ == "__main__":
    # Read the job name and SQL file path from the command line.
    # describe → build prompt → ask → extract
    # Save it to jobs_pyspark/<job>.py and print where it went.
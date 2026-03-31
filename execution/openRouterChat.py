"""
openRouterChat.py — CLI for OpenRouter

Usage:
  python openRouterChat.py                          # batch: all .txt in input/
  python openRouterChat.py <prompt.txt>             # single file, output next to input
  python openRouterChat.py <prompt.txt> <output>    # single file, explicit output path

Input file format:
  {model=<model_id>}
  Your prompt here...
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

TS_FMT   = "%m/%d/%y %I:%M:%S%p"
TS_WIDTH = len("03/19/26 12:04:02AM")
INDENT   = " " * (TS_WIDTH + 8)

def log(msg: str):
    ts = datetime.now().strftime(TS_FMT)
    print(f"{ts}        {msg}")

def sub(msg: str):
    print(f"{INDENT}{msg}")


def default_output_path(input_path: Path) -> Path:
    """Same directory as input, prefixed with output_."""
    return input_path.parent / f"output_{input_path.name}"


def process(input_path: Path, output_path: Path, client: OpenAI):
    log(f"Reading {input_path} ...")
    lines = input_path.read_text(encoding="utf-8").splitlines()
    model  = lines[0].strip().removeprefix("{model=").removesuffix("}")
    prompt = "\n".join(lines[1:]).strip()

    log("Calling OpenRouter API ...")
    sub(f"Model:  {model}")
    sub(f"Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

    start = time.time()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = round(time.time() - start)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(response.choices[0].message.content, encoding="utf-8")
    log(f"Written to {output_path}")
    sub(f"Done ({elapsed}s elapsed)")


def main():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not set. Add it to .env in the project root.")
        sys.exit(1)

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    args = sys.argv[1:]

    if not args:
        # Batch mode: process every .txt in input/
        input_dir = ROOT / "input"
        txt_files = sorted(input_dir.glob("*.txt"))
        if not txt_files:
            print(f"No .txt files found in {input_dir}")
            sys.exit(0)
        log(f"Batch mode — {len(txt_files)} file(s) in {input_dir}")
        for f in txt_files:
            process(f, default_output_path(f), client)
    elif len(args) == 1:
        # Single file, output next to input
        input_path = Path(args[0])
        process(input_path, default_output_path(input_path), client)
    else:
        # Single file with explicit output path
        input_path  = Path(args[0])
        output_path = Path(args[1])
        process(input_path, output_path, client)


if __name__ == "__main__":
    main()

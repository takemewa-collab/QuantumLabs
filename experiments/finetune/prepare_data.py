#!/usr/bin/env python3
"""
prepare_data.py — Download and format a small multilingual instruction dataset.

Source: CohereForAI/aya_dataset (open / free, human-annotated, ~65 languages).
We pick a handful of languages, cap the number of rows per language so the set
stays small, convert each example to chat ("messages") format, and write
train/val JSONL files that train_lora.py consumes directly.

This step is CPU-only — no GPU required. Run it once before training.

Usage:
    python prepare_data.py
    python prepare_data.py --languages English Turkish Arabic --max-per-lang 500
"""

import argparse
import json
import os
from pathlib import Path

DEFAULT_LANGUAGES = [
    "English",
    "Turkish",
    "Arabic",
    "Spanish",
    "French",
    "Standard German",
    "Hindi",
    "Simplified Chinese",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prepare multilingual instruction data.")
    p.add_argument(
        "--dataset",
        default="CohereForAI/aya_dataset",
        help="HuggingFace dataset id (default: CohereForAI/aya_dataset).",
    )
    p.add_argument(
        "--languages",
        nargs="+",
        default=DEFAULT_LANGUAGES,
        help="Languages to keep (match the dataset's 'language' column).",
    )
    p.add_argument(
        "--max-per-lang",
        type=int,
        default=500,
        help="Max rows kept per language (keeps the set small).",
    )
    p.add_argument(
        "--val-ratio",
        type=float,
        default=0.05,
        help="Fraction of rows held out for validation.",
    )
    p.add_argument(
        "--out-dir",
        default=str(Path(__file__).parent / "data"),
        help="Where to write train.jsonl / val.jsonl.",
    )
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def to_messages(example: dict) -> dict:
    """Convert one aya_dataset row to chat format.

    aya_dataset columns include: inputs, targets, language, language_code, ...
    """
    return {
        "messages": [
            {"role": "user", "content": example["inputs"].strip()},
            {"role": "assistant", "content": example["targets"].strip()},
        ],
        "language": example.get("language", "unknown"),
    }


def main() -> None:
    args = parse_args()

    # Imported here so `--help` works without the heavy dependency installed.
    from datasets import load_dataset

    print(f"Loading {args.dataset} (split=train) ...")
    ds = load_dataset(args.dataset, split="train")

    wanted = set(args.languages)
    print(f"Filtering to languages: {sorted(wanted)}")
    ds = ds.filter(lambda ex: ex.get("language") in wanted)

    # Cap rows per language so the corpus stays small and balanced.
    per_lang_count: dict[str, int] = {}
    kept_indices = []
    ds = ds.shuffle(seed=args.seed)
    for i, lang in enumerate(ds["language"]):
        if per_lang_count.get(lang, 0) < args.max_per_lang:
            per_lang_count[lang] = per_lang_count.get(lang, 0) + 1
            kept_indices.append(i)
    ds = ds.select(kept_indices)

    print("Rows kept per language:")
    for lang, n in sorted(per_lang_count.items()):
        print(f"  {lang:20s} {n}")
    print(f"Total: {len(ds)} rows")

    ds = ds.map(to_messages, remove_columns=ds.column_names)

    # Train / validation split.
    split = ds.train_test_split(test_size=args.val_ratio, seed=args.seed)
    train_ds, val_ds = split["train"], split["test"]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_path = out_dir / "train.jsonl"
    val_path = out_dir / "val.jsonl"

    for path, subset in ((train_path, train_ds), (val_path, val_ds)):
        with open(path, "w", encoding="utf-8") as f:
            for row in subset:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Wrote {len(subset):5d} rows -> {path}")

    print("\nDone. Next: run train_lora.py on a GPU machine.")


if __name__ == "__main__":
    main()

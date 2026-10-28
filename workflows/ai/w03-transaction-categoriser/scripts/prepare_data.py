"""
Load a transactions CSV, clean the descriptions and write a stratified
train/validation/test split plus the label mapping.

The split seed is fixed (not the training seed) so every run of a campaign
shares the same split and this task stays cached across runs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata

import pandas as pd
from sklearn.model_selection import train_test_split

SPLIT_SEED = 42


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text))
    return re.sub(r"\s+", " ", text).strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--text_column", required=True)
    p.add_argument("--label_column", required=True)
    p.add_argument("--train", required=True)
    p.add_argument("--val", required=True)
    p.add_argument("--test", required=True)
    p.add_argument("--label_map", required=True)
    args = p.parse_args()

    df = pd.read_csv(args.csv, dtype=str)
    missing = {args.text_column, args.label_column} - set(df.columns)
    if missing:
        raise SystemExit(f"columns {sorted(missing)} not in CSV; found {list(df.columns)}")

    df = df[[args.text_column, args.label_column]].rename(
        columns={args.text_column: "text", args.label_column: "label"}
    )
    n_raw = len(df)
    df["text"] = df["text"].fillna("").map(clean)
    df["label"] = df["label"].fillna("").map(clean)
    df = df[(df["text"] != "") & (df["label"] != "")].drop_duplicates()
    # Stratification needs at least one example per class in each split.
    counts = df["label"].value_counts()
    rare = counts[counts < 10].index
    if len(rare):
        print(f"dropping {len(rare)} classes with <10 rows: {list(rare)}")
        df = df[~df["label"].isin(rare)]

    labels = sorted(df["label"].unique())
    train, rest = train_test_split(df, test_size=0.2, stratify=df["label"], random_state=SPLIT_SEED)
    val, test = train_test_split(rest, test_size=0.5, stratify=rest["label"], random_state=SPLIT_SEED)

    for split, path in ((train, args.train), (val, args.val), (test, args.test)):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        split.to_csv(path, index=False)
    with open(args.label_map, "w") as f:
        json.dump({"labels": labels, "label2id": {l: i for i, l in enumerate(labels)}}, f, indent=2)

    print(
        f"{n_raw} rows -> {len(df)} clean, {len(labels)} classes; "
        f"train {len(train)} / val {len(val)} / test {len(test)}"
    )


if __name__ == "__main__":
    main()

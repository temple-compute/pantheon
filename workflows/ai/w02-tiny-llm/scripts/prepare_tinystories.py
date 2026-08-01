"""
Download + tokenize TinyStories into a flat-token HDF5 with the same {"tokens": int32[N]}
layout the base repo's pretrain data loader expects (data_loader/data_loader.py). Standalone
alternative to the cloned repo's scripts/prepare_pretrain_data.py, which is hardcoded to the
~900GB Pile corpus -- TinyStories (short, simple GPT-generated children's stories) is a couple
hundred MB, making it a fast, tiny pretraining set.
"""

from __future__ import annotations

import argparse
import os

import h5py
import numpy as np
import tiktoken
from datasets import load_dataset
from tqdm import tqdm

EOT_ID = 50256
WRITE_CHUNK = 2_000_000
ENC_BATCH = 1024


def tokenize_to_h5(split: str, out_path: str, max_docs: int | None) -> int:
    enc = tiktoken.get_encoding("r50k_base")
    ds = load_dataset("roneneldan/TinyStories", split=split)
    if max_docs:
        ds = ds.select(range(min(max_docs, len(ds))))

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    total = 0
    buf: list[int] = []
    with h5py.File(out_path, "w") as f:
        dset = f.create_dataset("tokens", (0,), maxshape=(None,), dtype="i4", chunks=(WRITE_CHUNK,))

        def flush():
            nonlocal total, buf
            if not buf:
                return
            arr = np.asarray(buf, dtype=np.int32)
            dset.resize(total + arr.size, axis=0)
            dset[total: total + arr.size] = arr
            total += arr.size
            buf = []

        docs: list[str] = []
        for row in tqdm(ds, desc=f"tok[{split}]"):
            docs.append(row["text"])
            if len(docs) >= ENC_BATCH:
                for ids in enc.encode_ordinary_batch(docs):
                    buf.extend(ids)
                    buf.append(EOT_ID)
                docs = []
                if len(buf) >= WRITE_CHUNK:
                    flush()
        if docs:
            for ids in enc.encode_ordinary_batch(docs):
                buf.extend(ids)
                buf.append(EOT_ID)
        flush()
    print(f"wrote {total:,} tokens -> {out_path}")
    return total


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=["train", "validation"], required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max_docs", type=int, default=None, help="cap docs for a fast tiny run")
    args = p.parse_args()
    tokenize_to_h5(args.split, args.out, args.max_docs)


if __name__ == "__main__":
    main()

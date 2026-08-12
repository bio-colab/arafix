#!/usr/bin/env python3
"""Optional Arabic semantic-preservation evaluation.

This is an evaluation tool, not a runtime dependency of arafix. It accepts a
JSONL manifest with real reference/hypothesis text pairs and records model,
revision, dependency versions, page/document IDs, and cosine similarity.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModel, AutoTokenizer


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean_pool(last_hidden: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    weights = mask.unsqueeze(-1).expand(last_hidden.size()).float()
    return (last_hidden * weights).sum(dim=1) / weights.sum(dim=1).clamp(min=1e-9)


def embed(texts: list[str], tokenizer: Any, model: Any, max_length: int) -> torch.Tensor:
    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    with torch.inference_mode():
        output = model(**encoded)
    return torch.nn.functional.normalize(mean_pool(output.last_hidden_state, encoded["attention_mask"]), p=2, dim=1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True, help="JSONL with id, reference, hypothesis")
    parser.add_argument("--model", default="aubmindlab/bert-base-arabert")
    parser.add_argument("--revision", default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit("manifest is empty")
    required = {"id", "reference", "hypothesis"}
    missing = required - set(rows[0])
    if missing:
        raise SystemExit(f"manifest rows missing fields: {sorted(missing)}")

    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    model = AutoModel.from_pretrained(args.model, revision=args.revision)
    model.eval()
    scores: list[dict[str, Any]] = []
    for start in range(0, len(rows), args.batch_size):
        batch = rows[start : start + args.batch_size]
        ref = embed([row["reference"] for row in batch], tokenizer, model, args.max_length)
        hyp = embed([row["hypothesis"] for row in batch], tokenizer, model, args.max_length)
        sims = (ref * hyp).sum(dim=1).tolist()
        for row, score in zip(batch, sims):
            scores.append({"id": row["id"], "cosine_similarity": float(score), "source": row.get("source")})

    payload = {
        "model": args.model,
        "revision": args.revision,
        "manifest": str(args.manifest),
        "manifest_sha256": sha256_file(args.manifest),
        "n": len(scores),
        "mean_cosine": sum(x["cosine_similarity"] for x in scores) / len(scores),
        "min_cosine": min(x["cosine_similarity"] for x in scores),
        "max_cosine": max(x["cosine_similarity"] for x in scores),
        "scores": scores,
        "packages": {name: importlib.metadata.version(name) for name in ("torch", "transformers")},
        "device": "cuda" if torch.cuda.is_available() else "cpu",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("model", "n", "mean_cosine", "min_cosine", "max_cosine", "device")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

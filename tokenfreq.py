#!/usr/bin/env python3
"""
tokenfreq.py — Token frequency analyser for Claude conversation exports.

Tokenises all messages using the Claude tokenizer (Xenova/claude-tokenizer via
HuggingFace Hub), then scores unigrams, bigrams, and trigrams by frequency.

Usage:
    python tokenfreq.py                        # analyse claude-export/, print top 50
    python tokenfreq.py --export path/to/dir   # custom export folder
    python tokenfreq.py --top 100              # show more results
    python tokenfreq.py --role user            # filter to user messages only
    python tokenfreq.py --role assistant       # filter to assistant messages only
    python tokenfreq.py --out results.json     # also save full tables to JSON
    python tokenfreq.py --ngram 2              # only bigrams
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# ── Tokenizer setup ───────────────────────────────────────────────────────────

def load_tokenizer():
    """Load Claude tokenizer; fall back to GPT-2 if unavailable."""
    try:
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
        path = hf_hub_download(
            repo_id="Xenova/claude-tokenizer",
            filename="tokenizer.json",
            local_files_only=False,
        )
        tok = Tokenizer.from_file(path)
        tok.no_truncation()
        return tok, "Claude (Xenova/claude-tokenizer)"
    except Exception as e:
        print(f"[warn] Claude tokenizer unavailable ({e}), falling back to GPT-2.", file=sys.stderr)
    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained("gpt2")
        return tok, "GPT-2 (fallback)"
    except Exception as e:
        raise RuntimeError(f"No tokenizer available: {e}")

# ── Data loading (shared logic with browse.py) ────────────────────────────────

def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""

def iter_messages(export_dir: Path, role_filter: str | None):
    """Yield (role, text) for every message across all sources."""

    # ── Cloud export
    cloud_path = export_dir / "conversations.json"
    if cloud_path.exists():
        with open(cloud_path, encoding="utf-8") as f:
            data = json.load(f)
        convs = data if isinstance(data, list) else data.get("value", data)
        for conv in convs:
            for m in conv.get("chat_messages", []):
                role = m.get("sender", "human")
                if role_filter and role != role_filter:
                    continue
                text = m.get("text") or extract_text(m.get("content", ""))
                if text:
                    yield role, text

    # ── Local JSONL transcripts
    projects_dir = export_dir / "local" / "dot-claude" / "projects"
    if projects_dir.exists():
        for jsonl in projects_dir.rglob("*.jsonl"):
            try:
                with open(jsonl, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if entry.get("type") not in ("user", "assistant"):
                            continue
                        msg = entry.get("message", {})
                        role = msg.get("role", entry["type"])
                        if role_filter and role != role_filter:
                            continue
                        text = extract_text(msg.get("content", ""))
                        if text:
                            yield role, text
            except Exception:
                pass

# ── Tokenisation + n-gram counting ───────────────────────────────────────────

def tokenise(tokenizer, tok_name: str, text: str) -> list[int]:
    """Return token ID list regardless of tokenizer type."""
    if "Xenova" in tok_name or hasattr(tokenizer, "encode") and hasattr(tokenizer.encode(text[:10]), "ids"):
        return tokenizer.encode(text).ids
    # transformers tokenizer
    return tokenizer.encode(text, add_special_tokens=False)

def decode_ids(tokenizer, tok_name: str, ids: list[int]) -> str:
    if "Xenova" in tok_name:
        return tokenizer.decode(ids)
    return tokenizer.decode(ids, skip_special_tokens=True)

def count_ngrams(token_ids: list[int], n: int) -> Counter:
    c: Counter = Counter()
    for i in range(len(token_ids) - n + 1):
        c[tuple(token_ids[i:i + n])] += 1
    return c

# ── Display ───────────────────────────────────────────────────────────────────

def print_table(title: str, counter: Counter, tokenizer, tok_name: str, top: int):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")
    print(f"  {'Rank':<6} {'Count':>8}  {'Freq%':>7}  Token sequence")
    print(f"  {'-'*6} {'-'*8}  {'-'*7}  {'-'*30}")
    total = sum(counter.values())
    for rank, (ids, count) in enumerate(counter.most_common(top), 1):
        decoded = decode_ids(tokenizer, tok_name, list(ids))
        decoded_repr = repr(decoded)[1:-1][:45]
        freq = count / total * 100
        print(f"  {rank:<6} {count:>8}  {freq:>6.3f}%  {decoded_repr}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Token frequency analyser for Claude exports")
    parser.add_argument("--export", default="claude-export", help="Export folder (default: ./claude-export)")
    parser.add_argument("--top",    type=int, default=50,    help="Top N results per table (default: 50)")
    parser.add_argument("--role",   choices=["user", "human", "assistant"], default=None,
                        help="Filter to one role (default: all)")
    parser.add_argument("--ngram",  type=int, default=None,
                        help="Only show this n (1=unigram, 2=bigram, 3=trigram; default: all)")
    parser.add_argument("--out",    default=None, help="Save full frequency tables to JSON file")
    args = parser.parse_args()

    export_dir = Path(args.export)
    if not export_dir.exists():
        print(f"Error: export folder not found: {export_dir}", file=sys.stderr)
        sys.exit(1)

    # normalise role alias
    role_filter = "human" if args.role == "user" else args.role

    print("Loading tokenizer…")
    tokenizer, tok_name = load_tokenizer()
    print(f"Using: {tok_name}\n")

    print("Loading and tokenising messages…")
    all_ids: list[int] = []
    msg_count = 0
    for role, text in iter_messages(export_dir, role_filter):
        ids = tokenise(tokenizer, tok_name, text)
        all_ids.extend(ids)
        msg_count += 1
        if msg_count % 500 == 0:
            print(f"  {msg_count} messages, {len(all_ids):,} tokens…", end="\r")

    print(f"\nTotal: {msg_count:,} messages · {len(all_ids):,} tokens")

    ngrams_to_show = [args.ngram] if args.ngram else [1, 2, 3]
    tables = {}
    for n in ngrams_to_show:
        counter = count_ngrams(all_ids, n)
        label = {1: "Unigrams", 2: "Bigrams", 3: "Trigrams"}.get(n, f"{n}-grams")
        tables[label] = counter
        role_label = f" [{role_filter} only]" if role_filter else ""
        print_table(f"{label}{role_label}  (vocab size: {len(counter):,})", counter, tokenizer, tok_name, args.top)

    if args.out:
        out = {}
        for label, counter in tables.items():
            decoded_counter = {}
            for ids, count in counter.most_common():
                key = decode_ids(tokenizer, tok_name, list(ids))
                decoded_counter[key] = count
            out[label] = decoded_counter
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved to {args.out}")

if __name__ == "__main__":
    main()

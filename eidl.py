#!/usr/bin/env python3
"""
EIDL — Efficient Internal Dialogue Language Translator
Bidirectional: Natural Language ↔ EIDL compressed notation

Usage:
    python eidl.py                  # interactive REPL
    python eidl.py -m nl2eidl       # start in NL→EIDL mode
    python eidl.py -m eidl2nl       # start in EIDL→NL mode
    python eidl.py -s "some text"   # single-shot translate (auto-detects direction)
    echo "some text" | python eidl.py -s -   # pipe mode
"""

import anthropic
import argparse
import sys
import os
import re

# ── Prompts ──────────────────────────────────────────────────────────────────

LEXICON_BLOCK = """
LEXICON:
  Epistemic:     cnf=confirm, hyp=hypothesis, inf=inference, asm=assumption,
                 rec=recall(training), obs=observe(context), gap=missing-info,
                 prb=probability, val=validate, stl=stale, amg=ambiguous
  Cognitive ops: dcp=decompose, mrg=merge, rtr=retrieve, flt=filter, rnk=rank,
                 pln=plan, rev=revise, chk=check, abs=abstract, spc=specialise,
                 sim=simulate, trk=track
  Context mgmt:  ctx=context, ctxΔ=context-change, ctxL=context-load,
                 pin=must-retain, drp=drop/compress, smz=summarize, ptr=pointer,
                 anc=anchor, scop=scope, cpt=checkpoint, src=source
  Task states:   prq=prerequisite, blk=blocked, pnd=pending, don=done, fal=fail,
                 alt=alternate, itr=iterate, mst=must, shl=should, cst=cost
  Relational:    usr=user, self=model, sys=system-prompt, tsk=task, dta=data,
                 tol=tool, out=output, prv=previous, dom=domain, cnd=condition

OPERATORS:
  →  implies / leads-to        ←  derived-from / input
  ↔  bidirectional             ⊕  merge / integrate
  ⊗  conflict / reject         ↑  prioritise    ↓  deprioritise
  ∅  null / no evidence        ≈  approximate
  !  flag / alert              ?  unresolved query
  @  cite / reference          ∴  therefore
  ∵  because                   ≡  definitional equivalence
  …  elision (compressible)    ·  statement separator

CONFIDENCE PREFIXES (prepend to root):
  +  high / verified     ~  medium / plausible
  ∂  low / speculative   !  needs flag    ?  open question

SCOPE BRACKETS:
  [label]   epistemic tag for a claim
  {mem}     operating from training memory
  {ctx}     reading from context window
  (n)       ordinal step or priority number
  %nn       numeric probability or progress
"""

SYS_NL2EIDL = f"""You are an EIDL encoder. EIDL is a token-efficient conlang for AI internal reasoning.
{LEXICON_BLOCK}
Convert the input natural-language reasoning into compact EIDL notation.
Rules:
- Aim for 80%+ token reduction
- Use · as statement separator
- Chain roots with operators: usr→int, dcp tsk→(3)sub, !ctxL→smz prv
- Apply confidence prefixes: +cnf, ~hyp, ∂inf, ?amg
- Use scope brackets for operational mode: rec{{mem}}, obs{{ctx}}
- Return ONLY the EIDL — no explanation, no markdown, no preamble
"""

SYS_EIDL2NL = f"""You are an EIDL decoder. EIDL is a token-efficient conlang for AI internal reasoning.
{LEXICON_BLOCK}
Expand the EIDL input into clear, natural-language internal reasoning.
Rules:
- Preserve all epistemic nuance (confidence levels, sources, flags)
- Write as first-person present-tense internal monologue
- Be concise but complete — don't pad unnecessarily
- Return ONLY the expanded natural language — no preamble
"""

# ── Heuristic: detect direction ───────────────────────────────────────────────

EIDL_OPERATORS = set("→←↔⊕⊗↑↓∅≈!?@∴∵≡…·∂")
EIDL_ROOTS = {
    "cnf","hyp","inf","asm","rec","obs","gap","prb","val","stl","amg",
    "dcp","mrg","rtr","flt","rnk","pln","rev","chk","abs","spc","sim","trk",
    "ctx","pin","drp","smz","ptr","anc","scop","cpt","src",
    "prq","blk","pnd","don","fal","alt","itr","mst","shl","cst",
    "usr","self","sys","tsk","dta","tol","out","prv","dom","cnd",
    "ctxL","ctxΔ","ctxl",
}

def detect_direction(text: str) -> str:
    """Return 'eidl2nl' if text looks like EIDL, else 'nl2eidl'."""
    op_count = sum(1 for ch in text if ch in EIDL_OPERATORS)
    words = re.findall(r"[a-zA-ZΔ]+", text.lower())
    root_count = sum(1 for w in words if w in EIDL_ROOTS)
    word_count = max(len(text.split()), 1)
    if op_count >= 2 or root_count >= 2 or (root_count >= 1 and word_count <= 8):
        return "eidl2nl"
    return "nl2eidl"

# ── Token counting (rough) ────────────────────────────────────────────────────

def rough_tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.3))

# ── Core translate function ───────────────────────────────────────────────────

def translate(text: str, mode: str, client: anthropic.Anthropic) -> dict:
    system = SYS_NL2EIDL if mode == "nl2eidl" else SYS_EIDL2NL
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": text}],
    )
    output = message.content[0].text.strip()
    in_tok  = rough_tokens(text)
    out_tok = rough_tokens(output)
    compression = round((1 - out_tok / in_tok) * 100) if mode == "nl2eidl" else None
    return {
        "output": output,
        "in_tokens":    in_tok,
        "out_tokens":   out_tok,
        "compression":  compression,
        "usage":        message.usage,
    }

# ── Display helpers ───────────────────────────────────────────────────────────

CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def no_color() -> bool:
    return not sys.stdout.isatty() or os.environ.get("NO_COLOR")

def c(code: str, text: str) -> str:
    return text if no_color() else f"{code}{text}{RESET}"

def print_result(result: dict, mode: str) -> None:
    label = "EIDL" if mode == "nl2eidl" else "English"
    print()
    print(c(CYAN, f"  {label}:"), c(BOLD, result["output"]))
    if mode == "nl2eidl" and result["compression"] is not None:
        colour = GREEN if result["compression"] > 60 else YELLOW
        print(c(DIM, f"\n  ~{result['in_tokens']} tok → ~{result['out_tokens']} tok  ") +
              c(colour, f"({result['compression']}% compression)"))
    print()

def mode_label(mode: str) -> str:
    return "NL → EIDL" if mode == "nl2eidl" else "EIDL → NL"

# ── REPL ──────────────────────────────────────────────────────────────────────

HELP_TEXT = """
  Commands:
    /nl       switch to NL → EIDL mode
    /eidl     switch to EIDL → NL mode
    /auto     auto-detect direction per input
    /help     show this message
    /quit     exit  (also: /q, Ctrl-C, Ctrl-D)
"""

def repl(client: anthropic.Anthropic, initial_mode: str = "nl2eidl") -> None:
    mode = initial_mode
    auto = False

    print(c(BOLD, "\n  EIDL Translator"))
    print(c(DIM,  "  Efficient Internal Dialogue Language  ·  v0.1"))
    print(c(DIM,  f"  Mode: {mode_label(mode)}  ·  type /help for commands\n"))

    while True:
        try:
            prompt_str = c(CYAN, f"[{'auto' if auto else mode_label(mode)}]") + " › "
            line = input(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        if line.startswith("/"):
            cmd = line.lower()
            if cmd in ("/q", "/quit", "/exit"):
                break
            elif cmd == "/nl":
                mode, auto = "nl2eidl", False
                print(c(DIM, f"  → {mode_label(mode)}"))
            elif cmd == "/eidl":
                mode, auto = "eidl2nl", False
                print(c(DIM, f"  → {mode_label(mode)}"))
            elif cmd == "/auto":
                auto = True
                print(c(DIM, "  → auto-detect mode"))
            elif cmd == "/help":
                print(HELP_TEXT)
            else:
                print(c(YELLOW, f"  Unknown command: {line}"))
            continue

        effective_mode = detect_direction(line) if auto else mode
        try:
            result = translate(line, effective_mode, client)
            print_result(result, effective_mode)
        except anthropic.APIError as e:
            print(c(YELLOW, f"  API error: {e}"))

# ── Single-shot mode ──────────────────────────────────────────────────────────

def single_shot(text: str, mode: str | None, client: anthropic.Anthropic) -> None:
    if text == "-":
        text = sys.stdin.read().strip()
    effective_mode = mode if mode else detect_direction(text)
    result = translate(text, effective_mode, client)
    if sys.stdout.isatty():
        print_result(result, effective_mode)
    else:
        print(result["output"])

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="EIDL ↔ Natural Language translator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["nl2eidl", "eidl2nl"],
        default=None,
        help="translation direction (default: auto-detect for -s, nl2eidl for REPL)",
    )
    parser.add_argument(
        "-s", "--single",
        metavar="TEXT",
        default=None,
        help='translate a single string and exit; use "-" to read from stdin',
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    if args.single is not None:
        single_shot(args.single, args.mode, client)
    else:
        repl(client, initial_mode=args.mode or "nl2eidl")

if __name__ == "__main__":
    main()

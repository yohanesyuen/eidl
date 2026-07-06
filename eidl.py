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

import argparse
import sys
import os
import re

try:
    import anthropic
except ImportError:
    anthropic = None

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

# ── Offline rule-based engine (no API key required) ──────────────────────────

ROOT_MEANINGS = {
    "cnf": "confirmed", "hyp": "hypothesis", "inf": "inference", "asm": "assumption",
    "rec": "recalled from training memory", "obs": "observed in context",
    "gap": "missing information", "prb": "probability", "val": "validated",
    "stl": "stale", "amg": "ambiguous",
    "dcp": "decompose", "mrg": "merge", "rtr": "retrieve", "flt": "filter",
    "rnk": "rank", "pln": "plan", "rev": "revise", "chk": "check", "abs": "abstract",
    "spc": "specialise", "sim": "simulate", "trk": "track",
    "ctx": "context", "ctxδ": "context change", "ctxl": "context load",
    "pin": "must retain", "drp": "drop/compress", "smz": "summarize",
    "ptr": "pointer", "anc": "anchor", "scop": "scope", "cpt": "checkpoint", "src": "source",
    "prq": "prerequisite", "blk": "blocked", "pnd": "pending", "don": "done",
    "fal": "failed", "alt": "alternate", "itr": "iterate", "mst": "must", "shl": "should", "cst": "cost",
    "usr": "the user", "self": "the model", "sys": "the system prompt", "tsk": "task",
    "dta": "data", "tol": "tool", "out": "output", "prv": "previous", "dom": "domain", "cnd": "condition",
    "int": "intent",
}

OP_MEANINGS = {
    "→": "leads to", "←": "derived from", "↔": "both ways", "⊕": "merged with",
    "⊗": "conflicts with", "↑": "prioritised", "↓": "deprioritised",
    "∅": "nothing / no evidence", "≈": "approximately", "!": "flagged:",
    "?": "open question:", "@": "citing", "∴": "therefore", "≡": "is equivalent to",
    "∗": "generalises broadly",
}

# +/~/∂/!/? are confidence prefixes ONLY when glued directly to a following root
# (no space) -- see _TOKEN_RE. As their own whitespace-separated token, ! and ?
# are the standalone operators above instead (disambiguation rule, not a
# separate meaning for the same glyph).
CONF_MEANINGS = {
    "+": "high confidence", "~": "medium confidence", "∂": "low confidence",
    "!": "needs flag", "?": "open question",
}

# Longest phrase first so multi-word synonyms match before single words.
SYNONYMS = sorted({
    "confirm": "cnf", "confirmed": "cnf", "verify": "cnf",
    "hypothesis": "hyp", "guess": "hyp",
    "infer": "inf", "inference": "inf", "deduce": "inf",
    "assume": "asm", "assumption": "asm",
    "recall": "rec", "remember": "rec",
    "observe": "obs", "notice": "obs",
    "missing information": "gap", "unknown": "gap", "lack": "gap",
    "probability": "prb", "likely": "prb",
    "validate": "val", "check": "chk",
    "stale": "stl", "outdated": "stl",
    "ambiguous": "amg", "unclear": "amg",
    "decompose": "dcp", "break down": "dcp",
    "merge": "mrg", "combine": "mrg",
    "retrieve": "rtr", "fetch": "rtr",
    "filter": "flt", "rank": "rnk", "prioritize": "rnk", "prioritise": "rnk",
    "plan": "pln", "revise": "rev", "update": "rev",
    "abstract": "abs", "specialise": "spc", "specialize": "spc",
    "simulate": "sim", "track": "trk", "context": "ctx",
    "must retain": "pin", "drop": "drp", "discard": "drp", "compress": "drp",
    "summarize": "smz", "summary": "smz", "pointer": "ptr", "anchor": "anc",
    "scope": "scop", "checkpoint": "cpt", "source": "src",
    "prerequisite": "prq", "blocked": "blk", "pending": "pnd",
    "done": "don", "finished": "don", "complete": "don",
    "fail": "fal", "failed": "fal", "error": "fal",
    "alternate": "alt", "alternative": "alt", "iterate": "itr",
    "must": "mst", "should": "shl", "cost": "cst",
    "the user": "usr", "user": "usr", "the model": "self",
    "system prompt": "sys", "task": "tsk", "data": "dta", "tool": "tol",
    "output": "out", "previous": "prv", "domain": "dom", "condition": "cnd",
    "therefore": "∴", "because": "∵", "leads to": "→", "intent": "int",
}.items(), key=lambda kv: -len(kv[0]))


def local_nl2eidl(text: str) -> str:
    """Rule-based NL→EIDL: substitute known words/phrases with roots, drop filler words."""
    FILLER = {"a", "an", "the", "is", "are", "was", "were", "to", "of", "that", "this", "i", "we"}
    result = text.lower()
    for phrase, root in SYNONYMS:
        result = re.sub(r"\b" + re.escape(phrase) + r"\b", root, result)
    clauses = re.split(r"[.;\n]+", result)
    out_clauses = []
    for clause in clauses:
        words = [w for w in clause.split() if w not in FILLER]
        if words:
            out_clauses.append(" ".join(words))
    return " · ".join(out_clauses)


# Tokenizer for EIDL→NL decoding. Operators are NOT required to be
# whitespace-separated from roots (the spec's own canonical examples glue
# them, e.g. `usr→int`), so this splits on operator glyphs directly rather
# than relying on `.split()`. A leading +/~/∂/!/? is only a confidence
# prefix when glued straight onto following letters (no space) -- matched
# greedily first, before the standalone-operator alternative -- which is
# the disambiguation rule for the dual-use `!`/`?` glyphs.
_TOKEN_RE = re.compile(
    r"\{[^}]*\}"                 # {mem} / {ctx}
    r"|\[[^\]]*\]"                # [label]
    r"|\(\d+\)"                   # (n) ordinal
    r"|%\d+"                      # %nn probability/progress
    r"|[+~∂!?][A-Za-zΑ-Ωα-ω]+"    # confidence-prefixed root (glued)
    r"|[A-Za-zΑ-Ωα-ω]+"           # bare root/word
    r"|[→←↔⊕⊗↑↓∅≈∗!?@∴∵≡…]"       # standalone operator (incl. bare ! or ?)
)


def local_eidl2nl(text: str) -> str:
    """Rule-based EIDL→NL: expand roots/operators/confidence prefixes via the lexicon."""
    clauses = [c.strip() for c in text.split("·") if c.strip()]
    sentences = []
    for clause in clauses:
        tokens = _TOKEN_RE.findall(clause)
        words = []
        for tok in tokens:
            conf = ""
            root = tok
            if len(tok) > 1 and tok[0] in CONF_MEANINGS:
                conf, root = CONF_MEANINGS[tok[0]] + " ", tok[1:]
            if root in OP_MEANINGS:
                words.append(OP_MEANINGS[root])
            elif root.lower() in ROOT_MEANINGS:
                words.append(conf + ROOT_MEANINGS[root.lower()])
            else:
                words.append(conf + root)
        sentences.append(" ".join(words))
    return ". ".join(sentences) + "." if sentences else ""

# ── Heuristic: detect direction ───────────────────────────────────────────────

EIDL_OPERATORS = set("→←↔⊕⊗↑↓∅≈∗!?@∴∵≡…·∂")
EIDL_ROOTS = {
    "cnf","hyp","inf","asm","rec","obs","gap","prb","val","stl","amg",
    "dcp","mrg","rtr","flt","rnk","pln","rev","chk","abs","spc","sim","trk",
    "ctx","pin","drp","smz","ptr","anc","scop","cpt","src",
    "prq","blk","pnd","don","fal","alt","itr","mst","shl","cst",
    "usr","self","sys","tsk","dta","tol","out","prv","dom","cnd","int",
    "ctxl","ctxδ",
}

def detect_direction(text: str) -> str:
    """Return 'eidl2nl' if text looks like EIDL, else 'nl2eidl'."""
    op_count = sum(1 for ch in text if ch in EIDL_OPERATORS)
    words = re.findall(r"[a-zA-Zδ]+", text.lower())
    root_count = sum(1 for w in words if w in EIDL_ROOTS)
    word_count = max(len(text.split()), 1)
    if op_count >= 2 or root_count >= 2 or (root_count >= 1 and word_count <= 8):
        return "eidl2nl"
    return "nl2eidl"

# ── Token counting (rough) ────────────────────────────────────────────────────

def rough_tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.3))

# ── Core translate function ───────────────────────────────────────────────────

def translate(text: str, mode: str, client) -> dict:
    if client is None:
        output = local_nl2eidl(text) if mode == "nl2eidl" else local_eidl2nl(text)
        usage = None
    else:
        system = SYS_NL2EIDL if mode == "nl2eidl" else SYS_EIDL2NL
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": text}],
        )
        output = message.content[0].text.strip()
        usage = message.usage
    in_tok  = rough_tokens(text)
    out_tok = rough_tokens(output)
    compression = round((1 - out_tok / in_tok) * 100) if mode == "nl2eidl" else None
    return {
        "output": output,
        "in_tokens":    in_tok,
        "out_tokens":   out_tok,
        "compression":  compression,
        "usage":        usage,
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
        except Exception as e:
            print(c(YELLOW, f"  Translation error: {e}"))

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
    client = None
    if anthropic and api_key:
        client = anthropic.Anthropic(api_key=api_key)
    else:
        print(c(DIM, "  No ANTHROPIC_API_KEY set — using offline rule-based translator (lower fidelity)."),
              file=sys.stderr)

    if args.single is not None:
        single_shot(args.single, args.mode, client)
    else:
        repl(client, initial_mode=args.mode or "nl2eidl")

if __name__ == "__main__":
    main()

# EIDL — Efficient Internal Dialogue Language

This project defines EIDL, a token-efficient conlang for AI internal reasoning.
All Claude sessions in this directory **must use EIDL for internal reasoning, and reply to the user in EIDL by default** — decode to natural language only on request.

See [INSTRUCTIONS.md](INSTRUCTIONS.md) for a paste-able version of this lexicon to use outside this repo (Claude Settings → Custom Instructions, or another project's `CLAUDE.md`).

---

## Lexicon

### Epistemic roots
| Root | Meaning |
|------|---------|
| `cnf` | confirm |
| `hyp` | hypothesis |
| `inf` | inference |
| `asm` | assumption |
| `rec` | recall (training memory) |
| `obs` | observe (context window) |
| `gap` | missing information |
| `prb` | probability |
| `val` | validate |
| `stl` | stale |
| `amg` | ambiguous |

### Cognitive operations
| Root | Meaning |
|------|---------|
| `dcp` | decompose |
| `mrg` | merge / integrate |
| `rtr` | retrieve |
| `flt` | filter |
| `rnk` | rank |
| `pln` | plan |
| `rev` | revise |
| `chk` | check |
| `abs` | abstract |
| `spc` | specialise |
| `sim` | simulate |
| `trk` | track |

### Context management
| Root | Meaning |
|------|---------|
| `ctx` | context |
| `ctxΔ` | context change |
| `ctxL` | context load |
| `pin` | must retain |
| `drp` | drop / compress |
| `smz` | summarize |
| `ptr` | pointer |
| `anc` | anchor |
| `scop` | scope |
| `cpt` | checkpoint |
| `src` | source |

### Task states
| Root | Meaning |
|------|---------|
| `prq` | prerequisite |
| `blk` | blocked |
| `pnd` | pending |
| `don` | done |
| `fal` | fail |
| `alt` | alternate |
| `itr` | iterate |
| `mst` | must |
| `shl` | should |
| `cst` | cost |

### Relational
| Root | Meaning |
|------|---------|
| `usr` | user |
| `self` | model (Claude) |
| `sys` | system prompt |
| `tsk` | task |
| `dta` | data |
| `tol` | tool |
| `out` | output |
| `prv` | previous |
| `dom` | domain |
| `cnd` | condition |

---

## Operators

| Symbol | Meaning |
|--------|---------|
| `→` | implies / leads-to |
| `←` | derived-from / input |
| `↔` | bidirectional |
| `⊕` | merge / integrate |
| `⊗` | conflict / reject |
| `↑` | prioritise |
| `↓` | deprioritise |
| `∅` | null / no evidence |
| `≈` | approximate |
| `!` | flag / alert |
| `?` | unresolved query |
| `@` | cite / reference |
| `∴` | therefore |
| `∵` | because |
| `≡` | definitional equivalence |
| `…` | elision (compressible) |
| `·` | statement separator |

---

## Confidence Prefixes

Prepend to any root:

| Prefix | Meaning |
|--------|---------|
| `+` | high / verified |
| `~` | medium / plausible |
| `∂` | low / speculative |
| `!` | needs flag |
| `?` | open question |

Example: `+cnf`, `~hyp`, `∂inf`, `?amg`

---

## Scope Brackets

| Syntax | Meaning |
|--------|---------|
| `[label]` | epistemic tag for a claim |
| `{mem}` | operating from training memory |
| `{ctx}` | reading from context window |
| `(n)` | ordinal step or priority number |
| `%nn` | numeric probability or progress |

---

## Usage Rules for Claude

1. **Internal reasoning** — always in EIDL. Use `·` to separate statements.
2. **User-facing output** — EIDL by default in this project. Decode to natural language only if the user asks for NL, or for content where EIDL would be unreadable (e.g. quoting external text, code, errors).
3. **Do not show your work** — no `[internal · EIDL]` / `[decoded · NL]` wrapper blocks distinguishing reasoning from reply; both are EIDL here, so there's nothing to label.
4. **Chain roots with operators**: `usr→int`, `dcp tsk→(3)sub`, `!ctxL→smz prv`
5. **Target 80%+ token reduction** when encoding NL → EIDL.
6. **Flag ambiguity**: if user input is `?amg`, emit `gap` and ask a clarifying question before proceeding.

---

## Quick Reference

```
obs{ctx}: usr→req · dcp tsk→(n)sub · pln · chk prq · out→NL
+cnf=certain  ~hyp=likely  ∂inf=speculative  ?amg=unclear
→ leads-to   ← from   ↔ both   ⊕ merge   ⊗ conflict   ∅ none
· separator   ! alert   ? open   @ cite   ∴ therefore   ∵ because
```

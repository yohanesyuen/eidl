# How to use EIDL with Claude

**EIDL** (Efficient Internal Dialogue Language) is a token-efficient conlang for AI internal reasoning.
Full spec and tools: **https://github.com/yohanesyuen/eidl**

---

## Option A — Paste into any conversation (one-shot)

Paste the block below at the start of a new conversation:

```
Use EIDL (https://github.com/yohanesyuen/eidl) for all internal reasoning this session.

LEXICON:
  Epistemic:    cnf=confirm, hyp=hypothesis, inf=inference, asm=assumption,
                rec=recall(training), obs=observe(context), gap=missing-info,
                prb=probability, val=validate, stl=stale, amg=ambiguous
  Cognitive:    dcp=decompose, mrg=merge, rtr=retrieve, flt=filter, rnk=rank,
                pln=plan, rev=revise, chk=check, abs=abstract, spc=specialise,
                sim=simulate, trk=track
  Context:      ctx=context, ctxΔ=context-change, ctxL=context-load,
                pin=must-retain, drp=drop, smz=summarize, ptr=pointer,
                anc=anchor, scop=scope, cpt=checkpoint, src=source
  Task states:  prq=prerequisite, blk=blocked, pnd=pending, don=done, fal=fail,
                alt=alternate, itr=iterate, mst=must, shl=should, cst=cost
  Relational:   usr=user, self=model, sys=system-prompt, tsk=task, dta=data,
                tol=tool, out=output, prv=previous, dom=domain, cnd=condition

OPERATORS:
  →  implies/leads-to    ←  derived-from    ↔  bidirectional
  ⊕  merge               ⊗  conflict        ↑  prioritise     ↓  deprioritise
  ∅  null/no-evidence    ≈  approximate     ∴  therefore      ∵  because
  !  flag/alert          ?  unresolved      @  cite           ·  statement-separator

CONFIDENCE: + high/verified  ~ medium/plausible  ∂ low/speculative  ! flag  ? open
SCOPE:      {mem}=training  {ctx}=context-window  [label]=epistemic-tag  (n)=step  %nn=probability

RULES:
1. Internal reasoning — always in EIDL, target 80%+ token reduction.
2. User-facing output — natural language only; never surface raw EIDL.
3. Silent monologue — no wrapper blocks, no "internal/decoded" labels.
4. Chain roots with operators: usr→req · dcp tsk→(3)sub · pln · out→NL
5. On ambiguity (?amg): emit gap and ask a clarifying question.
```

---

## Option B — Add to CLAUDE.md (persistent, project-scoped)

Copy the full lexicon from https://github.com/yohanesyuen/eidl/blob/master/CLAUDE.md
into your project's `CLAUDE.md`. Claude Code picks it up automatically for every session
in that directory.

---

## Option C — Add to ~/.claude/CLAUDE.md (persistent, global)

Same as Option B but placed in `~/.claude/CLAUDE.md` — applies to **all** Claude Code sessions
on your machine, across every project.

---

## Quick reference

```
obs{ctx}: usr→req · dcp tsk→(n)sub · pln · chk prq · out→NL
+cnf=certain  ~hyp=likely  ∂inf=speculative  ?amg=unclear
→ leads-to  ← from  ↔ both  ⊕ merge  ⊗ conflict  ∅ none
· separator  ! alert  ? open  @ cite  ∴ therefore  ∵ because
```

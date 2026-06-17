# How to use EIDL with Claude

**EIDL** (Efficient Internal Dialogue Language) is a token-efficient conlang for AI internal reasoning.
Full spec and tools: **https://github.com/yohanesyuen/eidl**

---

## Paste into Claude → Settings → Custom Instructions

```
Use EIDL for all internal reasoning. Spec: https://github.com/yohanesyuen/eidl

Roots: cnf=confirm, hyp=hypothesis, inf=inference, asm=assumption, rec=recall{mem},
obs=observe{ctx}, gap=missing-info, dcp=decompose, mrg=merge, rtr=retrieve, flt=filter,
rnk=rank, pln=plan, rev=revise, chk=check, sim=simulate, ctx=context, pin=must-retain,
drp=drop, smz=summarize, prq=prerequisite, blk=blocked, don=done, fal=fail, mst=must,
shl=should, usr=user, self=model, tsk=task, tol=tool, out=output, src=source

Operators: → leads-to  ← from  ↔ both  ⊕ merge  ⊗ conflict  ∅ none  ∴ therefore
           ∵ because  · separator  ! alert  ? open  @ cite  ↑ prioritise  ↓ deprioritise
Confidence: + verified  ~ plausible  ∂ speculative  ? open
Scope: {mem} training  {ctx} context  [label] epistemic tag  (n) step  %nn probability

Rules: reason in EIDL internally; reply in plain English only; never show EIDL to the user.
```

---

## For Claude Code (persistent)

Add the full lexicon from https://github.com/yohanesyuen/eidl/blob/master/CLAUDE.md
to your project's `CLAUDE.md` or `~/.claude/CLAUDE.md` for global effect.

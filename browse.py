#!/usr/bin/env python3
"""
browse.py — Claude conversation browser GUI
Loads cloud export + local JSONL transcripts and lets you browse by title.

Usage:
    python browse.py
    python browse.py --export claude-export   # path to export folder (default: ./claude-export)
"""

import argparse
import json
import os
import sys
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

# ── Data loading ──────────────────────────────────────────────────────────────

def ts_to_dt(ts) -> datetime | None:
    if not ts:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None

def fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")

def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    parts.append(f"[tool: {block.get('name','')}]")
                elif block.get("type") == "tool_result":
                    inner = block.get("content", "")
                    parts.append(f"[tool result: {extract_text(inner)[:120]}]")
        return "\n".join(parts)
    return ""

def load_cloud_export(export_dir: Path) -> list[dict]:
    path = export_dir / "conversations.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    convs = data if isinstance(data, list) else data.get("value", data)
    results = []
    for c in convs:
        msgs = []
        for m in c.get("chat_messages", []):
            text = m.get("text") or extract_text(m.get("content", ""))
            msgs.append({
                "role": m.get("sender", "human"),
                "text": text,
                "ts": fmt_dt(ts_to_dt(m.get("created_at"))),
            })
        results.append({
            "title": c.get("name") or "(untitled)",
            "source": "cloud",
            "updated": ts_to_dt(c.get("updated_at")),
            "messages": msgs,
        })
    return results

def load_jsonl_transcript(path: Path) -> list[dict]:
    msgs = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = entry.get("type")
                if role not in ("user", "assistant"):
                    continue
                msg = entry.get("message", {})
                text = extract_text(msg.get("content", ""))
                if not text:
                    continue
                msgs.append({
                    "role": msg.get("role", role),
                    "text": text,
                    "ts": fmt_dt(ts_to_dt(entry.get("timestamp"))),
                })
    except Exception:
        pass
    return msgs

def load_local_jsonl(export_dir: Path) -> list[dict]:
    projects_dir = export_dir / "local" / "dot-claude" / "projects"
    if not projects_dir.exists():
        return []

    # Build sessionId→title map from local-agent-mode-sessions metadata
    session_titles: dict[str, str] = {}
    agent_dir = export_dir / "local" / "local-agent-mode-sessions"
    if agent_dir.exists():
        for f in agent_dir.rglob("local_*.json"):
            try:
                meta = json.loads(f.read_text(encoding="utf-8"))
                cli_id = meta.get("cliSessionId", "")
                title = meta.get("title", "")
                if cli_id and title:
                    session_titles[cli_id] = title
            except Exception:
                pass

    results = []
    for jsonl in sorted(projects_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        session_id = jsonl.stem
        msgs = load_jsonl_transcript(jsonl)
        if not msgs:
            continue
        title = session_titles.get(session_id)
        if not title:
            first_user = next((m["text"] for m in msgs if m["role"] == "user"), "")
            title = first_user[:60].strip().replace("\n", " ") or session_id[:16]
        updated = ts_to_dt(jsonl.stat().st_mtime * 1000)
        results.append({
            "title": title,
            "source": "local",
            "updated": updated,
            "messages": msgs,
        })
    return results

def load_all(export_dir: Path) -> list[dict]:
    convs = load_cloud_export(export_dir) + load_local_jsonl(export_dir)
    convs.sort(key=lambda c: c["updated"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return convs

# ── GUI ───────────────────────────────────────────────────────────────────────

ROLE_COLORS = {
    "human":     ("#1a73e8", "User"),
    "user":      ("#1a73e8", "User"),
    "assistant": ("#188038", "Claude"),
}

class App(tk.Tk):
    def __init__(self, convs: list[dict]):
        super().__init__()
        self.title("Claude Conversation Browser")
        self.geometry("1200x750")
        self.minsize(800, 500)
        self.configure(bg="#f8f9fa")
        self._convs = convs
        self._filtered = convs
        self._build_ui()
        self._populate_list()

    def _build_ui(self):
        # ── fonts
        self._title_font  = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self._meta_font   = tkfont.Font(family="Segoe UI", size=8)
        self._role_font   = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self._msg_font    = tkfont.Font(family="Segoe UI", size=10)
        self._header_font = tkfont.Font(family="Segoe UI", size=13, weight="bold")

        # ── outer layout
        left  = tk.Frame(self, width=320, bg="#ffffff", relief="flat", bd=0)
        right = tk.Frame(self, bg="#f8f9fa")
        left.pack(side="left", fill="y")
        right.pack(side="left", fill="both", expand=True)
        left.pack_propagate(False)

        # ── left: search + list
        search_frame = tk.Frame(left, bg="#ffffff", pady=6, padx=8)
        search_frame.pack(fill="x")
        tk.Label(search_frame, text="Search", bg="#ffffff",
                 font=self._meta_font, fg="#666").pack(anchor="w")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._on_search())
        search_entry = tk.Entry(search_frame, textvariable=self._search_var,
                                relief="solid", bd=1, font=self._msg_font)
        search_entry.pack(fill="x", pady=(2, 0))

        count_frame = tk.Frame(left, bg="#ffffff", padx=8)
        count_frame.pack(fill="x")
        self._count_label = tk.Label(count_frame, text="", bg="#ffffff",
                                      font=self._meta_font, fg="#888")
        self._count_label.pack(anchor="w")

        sep = tk.Frame(left, height=1, bg="#e0e0e0")
        sep.pack(fill="x")

        list_frame = tk.Frame(left, bg="#ffffff")
        list_frame.pack(fill="both", expand=True)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        self._listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set,
            selectmode="single", relief="flat", bd=0,
            activestyle="none", highlightthickness=0,
            font=self._title_font, bg="#ffffff", fg="#202124",
            selectbackground="#e8f0fe", selectforeground="#1a73e8",
        )
        scrollbar.config(command=self._listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self._listbox.pack(fill="both", expand=True)
        self._listbox.bind("<<ListboxSelect>>", self._on_select)

        # ── right: header + messages
        header = tk.Frame(right, bg="#f8f9fa", padx=16, pady=10)
        header.pack(fill="x")
        self._conv_title = tk.Label(header, text="Select a conversation",
                                     font=self._header_font, bg="#f8f9fa", fg="#202124",
                                     wraplength=800, justify="left")
        self._conv_title.pack(anchor="w")
        self._conv_meta  = tk.Label(header, text="", font=self._meta_font,
                                     bg="#f8f9fa", fg="#888")
        self._conv_meta.pack(anchor="w")

        sep2 = tk.Frame(right, height=1, bg="#e0e0e0")
        sep2.pack(fill="x")

        msg_frame = tk.Frame(right, bg="#f8f9fa")
        msg_frame.pack(fill="both", expand=True, padx=16, pady=8)
        vbar = tk.Scrollbar(msg_frame, orient="vertical")
        self._msg_text = tk.Text(
            msg_frame, yscrollcommand=vbar.set,
            wrap="word", relief="flat", bd=0,
            font=self._msg_font, bg="#f8f9fa", fg="#202124",
            state="disabled", padx=4, pady=4,
            cursor="arrow",
        )
        vbar.config(command=self._msg_text.yview)
        vbar.pack(side="right", fill="y")
        self._msg_text.pack(fill="both", expand=True)

        # text tags
        self._msg_text.tag_config("user_role",  foreground="#1a73e8", font=self._role_font)
        self._msg_text.tag_config("asst_role",  foreground="#188038", font=self._role_font)
        self._msg_text.tag_config("ts",         foreground="#aaa",    font=self._meta_font)
        self._msg_text.tag_config("body",       font=self._msg_font,  spacing1=2, spacing3=8)
        self._msg_text.tag_config("divider",    foreground="#e0e0e0")

    def _populate_list(self):
        self._listbox.delete(0, "end")
        for c in self._filtered:
            badge = "☁" if c["source"] == "cloud" else "💻"
            self._listbox.insert("end", f"{badge}  {c['title']}")
        n = len(self._filtered)
        t = len(self._convs)
        self._count_label.config(text=f"{n} of {t} conversations")

    def _on_search(self):
        q = self._search_var.get().lower()
        self._filtered = [c for c in self._convs if q in c["title"].lower()] if q else self._convs
        self._populate_list()

    def _on_select(self, _event=None):
        sel = self._listbox.curselection()
        if not sel:
            return
        conv = self._filtered[sel[0]]
        self._conv_title.config(text=conv["title"])
        src  = "Cloud export" if conv["source"] == "cloud" else "Local (Claude Code)"
        date = fmt_dt(conv["updated"]) if conv["updated"] else ""
        self._conv_meta.config(text=f"{src}  ·  {date}  ·  {len(conv['messages'])} messages")
        self._render_messages(conv["messages"])

    def _render_messages(self, messages: list[dict]):
        t = self._msg_text
        t.config(state="normal")
        t.delete("1.0", "end")
        for i, m in enumerate(messages):
            role = m["role"]
            color, label = ROLE_COLORS.get(role, ("#555", role.capitalize()))
            tag = "user_role" if role in ("user", "human") else "asst_role"
            header = f"{label}"
            if m.get("ts"):
                t.insert("end", header, tag)
                t.insert("end", f"  {m['ts']}\n", "ts")
            else:
                t.insert("end", header + "\n", tag)
            t.insert("end", m["text"] + "\n", "body")
            if i < len(messages) - 1:
                t.insert("end", "─" * 60 + "\n", "divider")
        t.config(state="disabled")
        t.yview_moveto(0)

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Browse Claude conversations")
    parser.add_argument("--export", default="claude-export",
                        help="Path to the export folder (default: ./claude-export)")
    args = parser.parse_args()

    export_dir = Path(args.export)
    if not export_dir.exists():
        print(f"Error: export folder not found: {export_dir}", file=sys.stderr)
        sys.exit(1)

    print("Loading conversations…")
    convs = load_all(export_dir)
    print(f"Loaded {len(convs)} conversations.")

    app = App(convs)
    app.mainloop()

if __name__ == "__main__":
    main()

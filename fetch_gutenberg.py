#!/usr/bin/env python3
"""
fetch_gutenberg.py — download a Project Gutenberg book as clean Markdown
ready for pdf2audiobook.py (no Marker/OCR needed: Gutenberg text is already clean).

Usage:
    python fetch_gutenberg.py 50290            # by ebook number
    python fetch_gutenberg.py --picks          # all curated picks (see PICKS)
    python pdf2audiobook.py books/50290_Space_Station_1.md

What it does:
  - downloads https://www.gutenberg.org/cache/epub/<id>/pg<id>.txt
  - strips the Gutenberg license header/footer and transcriber notes
  - unwraps hard-wrapped lines into paragraphs (so narration doesn't pause mid-sentence)
  - turns CHAPTER / PART / roman-numeral lines into "## " headings for chapter splitting
"""
import argparse
import re
import sys
import urllib.request
from pathlib import Path

# Popular Gutenberg sci-fi with no standalone LibriVox recording (checked Oct 2026
# against archive.org's LibriVox collection). Short stories may still appear inside
# LibriVox multi-author collections.
PICKS = {
    50290: "Space Station 1 — Frank Belknap Long (1957 novel)",
    30434: "Occasion ... for Disaster — Randall Garrett & Laurence M. Janifer (novel)",
    23599: "The Big Fix — George O. Smith (novelette)",
    27609: "The Undersea Tube — L. Taylor Hansen (short story)",
    32562: "\"And That's How It Was, Officer\" — Ralph Sholto (short story)",
}

HEADING = re.compile(
    r"^(?:(?:CHAPTER|Chapter|PART|Part|BOOK|Book)\b.*"
    r"|[IVXLC]{1,7}\.?(?:\s.*)?"
    r"|EPILOGUE|PROLOGUE|Epilogue|Prologue)$"
)


def roman_to_int(r: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    for a, b in zip(r, r[1:] + " "):
        v = vals[a]
        total += -v if vals.get(b, 0) > v else v
    return total


def speakable_heading(h: str) -> str:
    """'CHAPTER IV' -> 'Chapter 4', 'XII' -> 'Chapter 12' (TTS reads roman numerals as letters)."""
    m = re.match(r"^(?:(CHAPTER|PART|BOOK)\s+)?([IVXLC]+)\b\.?\s*(.*)$", h, re.I)
    if m and re.fullmatch(r"[IVXLC]+", m.group(2)):
        word = (m.group(1) or "Chapter").capitalize()
        rest = m.group(3).strip(" .-—:")
        return f"{word} {roman_to_int(m.group(2).upper())}" + (f": {rest}" if rest else "")
    return h.title() if h.isupper() else h


def download(book_id: int) -> str:
    url = f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"
    req = urllib.request.Request(url, headers={"User-Agent": "pdfaudiobook/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8-sig", errors="replace")


def strip_boilerplate(txt: str) -> tuple[str, str]:
    txt = txt.replace("\r\n", "\n")
    title = re.search(r"^Title:\s*(.+)$", txt, re.M)
    title = title.group(1).strip() if title else "Untitled"
    start = re.search(r"^\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG.*$", txt, re.M)
    end = re.search(r"^\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG.*$", txt, re.M)
    body = txt[start.end() if start else 0: end.start() if end else len(txt)]
    # transcriber's notes, usually in a bracketed block
    body = re.sub(r"\[Transcriber'?s? [Nn]ote.*?\]", "", body, flags=re.S)
    body = re.sub(r"^\s*Transcriber'?s? [Nn]ote.*?(?:\n\s*\n)", "", body, flags=re.S | re.M)
    body = re.sub(r"^\s*(Produced by|E-?text prepared by).*?(?:\n\s*\n)", "", body,
                  flags=re.S | re.M | re.I)
    return title, body.strip()


def to_markdown(title: str, body: str) -> str:
    paras = re.split(r"\n\s*\n", body)
    out = [f"# {title}"]
    for p in paras:
        lines = [l.strip() for l in p.strip().split("\n") if l.strip()]
        if not lines:
            continue
        joined = " ".join(lines)
        if len(lines) <= 2 and len(joined) < 80 and HEADING.match(lines[0]):
            out.append("## " + speakable_heading(joined.rstrip(".")))
        elif re.fullmatch(r"[\s*.\-_=~]+", joined):  # scene-break rules
            continue
        else:
            joined = re.sub(r"_(.+?)_", r"\1", joined)  # Gutenberg _italics_
            out.append(joined)
    return "\n\n".join(out) + "\n"


def slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:n]


def fetch(book_id: int, out_dir: Path) -> Path:
    title, body = strip_boilerplate(download(book_id))
    md = to_markdown(title, body)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{book_id}_{slug(title)}.md"
    path.write_text(md, encoding="utf-8")
    n_ch = md.count("\n## ")
    print(f"{book_id}: {title}  ->  {path}  ({len(md):,} chars, {n_ch} headings)")
    return path


def main():
    ap = argparse.ArgumentParser(description="Gutenberg book -> clean Markdown")
    ap.add_argument("ids", nargs="*", type=int, help="Gutenberg ebook numbers")
    ap.add_argument("--picks", action="store_true", help="fetch all curated picks")
    ap.add_argument("--out", type=Path, default=Path("books"))
    a = ap.parse_args()
    ids = list(PICKS) if a.picks else a.ids
    if not ids:
        print("Curated picks:")
        for k, v in PICKS.items():
            print(f"  {k:>6}  {v}")
        sys.exit("\nPass ebook numbers or --picks.")
    for i in ids:
        try:
            fetch(i, a.out)
        except Exception as e:
            print(f"{i}: failed ({e})")


if __name__ == "__main__":
    main()

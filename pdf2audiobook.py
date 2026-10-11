#!/usr/bin/env python3
"""
pdf2audiobook.py — PDF -> clean chapters (Marker) -> MP3s (Kokoro TTS)

Setup (macOS):
    brew install ffmpeg espeak-ng llama.cpp
    python3.12 -m venv venv && source venv/bin/activate
    pip install marker-pdf kokoro soundfile numpy

Usage:
    # 1. Extract + clean text only (review/edit the .md before narrating)
    python pdf2audiobook.py book.pdf --text-only

    # 2. Narrate (reuses the cached book.md, skips chapters already done)
    python pdf2audiobook.py book.pdf

    # Or narrate Markdown directly (e.g. from fetch_gutenberg.py), skipping Marker
    python pdf2audiobook.py books/50290_Space_Station_1.md

Options:
    --out DIR          output folder (default: <book>_audio)
    --voice NAME       Kokoro voice (default af_heart; try am_michael, bf_emma, bm_george)
    --speed X          speech rate (default 1.0)
    --heading-level N  split chapters at this Markdown heading level or higher (default 2)
    --min-chars N      merge sections shorter than this into the next one (default 1500)
    --force-extract    re-run Marker even if the .md cache exists
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

SAMPLE_RATE = 24000  # Kokoro output rate


# ---------------------------------------------------------------- extraction
def extract_markdown(pdf: Path) -> str:
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered

    print("Loading Marker models (first run downloads ~2 GB)...")
    converter = PdfConverter(artifact_dict=create_model_dict())
    print(f"Converting {pdf.name} — this can take a while for a full book...")
    rendered = converter(str(pdf))
    text, _, _ = text_from_rendered(rendered)
    return text


# ---------------------------------------------------------------- cleaning
def clean_for_speech(md: str) -> str:
    s = md
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)                 # images
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)             # links -> text
    s = re.sub(r"<[^>]+>", "", s)                              # html tags/spans
    s = re.sub(r"^\s*\|.*\|\s*$", "", s, flags=re.M)           # tables
    s = re.sub(r"^\s*[-*_]{3,}\s*$", "", s, flags=re.M)        # horizontal rules
    s = re.sub(r"```.*?```", "", s, flags=re.S)                # code blocks
    s = re.sub(r"\[\^?\d+\]|\^\d+|(?<=[a-z.,;])\d{1,3}(?=\s)", "", s)  # footnote markers
    s = re.sub(r"^\s*\d{1,4}\s*$", "", s, flags=re.M)          # stray page numbers
    s = re.sub(r"(\*\*|__|\*|_|`)", "", s)                     # emphasis marks
    s = re.sub(r"^\s*[-*+]\s+", "", s, flags=re.M)             # bullet markers
    s = re.sub(r"^\s*>\s?", "", s, flags=re.M)                 # blockquotes
    s = re.sub(r"(\w)-\n(\w)", r"\1\2", s)                     # leftover hyphen breaks
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def split_chapters(md: str, level: int, min_chars: int):
    """Split on Markdown headings up to `level`; merge short sections forward."""
    pattern = re.compile(rf"^(#{{1,{level}}})\s+(.+?)\s*#*\s*$", re.M)
    marks = list(pattern.finditer(md))
    sections = []
    if not marks:
        return [("Full Text", md)]
    if marks[0].start() > 0 and md[: marks[0].start()].strip():
        sections.append(("Front Matter", md[: marks[0].start()]))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(md)
        title = re.sub(r"[*_`]", "", m.group(2)).strip()
        sections.append((title, md[m.end():end]))

    # Short sections (part titles, epigraphs, sub-headings) are folded into the
    # previous chapter; if there is none yet, they're spoken at the start of the next.
    merged, prefix = [], ""
    for title, body in sections:
        size = len(clean_for_speech(body))
        if title == "Front Matter":  # own track if substantial, else dropped
            if size >= 200:
                merged.append((title, body))
            continue
        if size >= min_chars:
            merged.append((title, (prefix + body) if prefix else body))
            prefix = ""
        elif merged and merged[-1][0] != "Front Matter":
            t, b = merged[-1]
            merged[-1] = (t, f"{b}\n\n{title}.\n\n{body}")
        else:
            prefix += f"{title}.\n\n{body}\n\n"
    if prefix:
        merged.append(("Remainder", prefix))
    return merged


def slug(text: str, n: int = 50) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:n] or "untitled"


# ---------------------------------------------------------------- audio
def narrate(chapters, out_dir: Path, voice: str, speed: float):
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    lang = voice[0]  # 'a' = American, 'b' = British
    pipeline = KPipeline(lang_code=lang)
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, (title, body) in enumerate(chapters, 1):
        mp3 = out_dir / f"{i:02d}_{slug(title)}.mp3"
        if mp3.exists():
            print(f"[{i}/{len(chapters)}] skip (done): {mp3.name}")
            continue
        text = f"{title}.\n\n{clean_for_speech(body)}"
        print(f"[{i}/{len(chapters)}] {title}  ({len(text):,} chars)")

        chunks = []
        for _, _, audio in pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+"):
            if audio is not None:
                chunks.append(np.asarray(audio))
                chunks.append(np.zeros(int(SAMPLE_RATE * 0.35), dtype=np.float32))  # paragraph pause
        if not chunks:
            print("   (no audio produced, skipping)")
            continue

        wav = mp3.with_suffix(".wav")
        sf.write(wav, np.concatenate(chunks), SAMPLE_RATE)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
             "-codec:a", "libmp3lame", "-qscale:a", "4",
             "-metadata", f"title={title}", "-metadata", f"track={i}", str(mp3)],
            check=True,
        )
        wav.unlink()


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="PDF -> chaptered MP3 audiobook")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--heading-level", type=int, default=2)
    ap.add_argument("--min-chars", type=int, default=1500)
    ap.add_argument("--text-only", action="store_true")
    ap.add_argument("--force-extract", action="store_true")
    a = ap.parse_args()

    if not a.pdf.exists():
        sys.exit(f"Not found: {a.pdf}")
    md_path = a.pdf.with_suffix(".md")
    out_dir = a.out or a.pdf.with_name(a.pdf.stem + "_audio")

    if a.pdf.suffix.lower() == ".md":  # already-clean text (e.g. from fetch_gutenberg.py)
        md_path = a.pdf
        md = md_path.read_text(encoding="utf-8")
    elif md_path.exists() and not a.force_extract:
        print(f"Using cached text: {md_path.name}")
        md = md_path.read_text(encoding="utf-8")
    else:
        md = extract_markdown(a.pdf)
        md_path.write_text(md, encoding="utf-8")
        print(f"Saved text: {md_path}")

    chapters = split_chapters(md, a.heading_level, a.min_chars)
    print(f"\n{len(chapters)} chapters:")
    for i, (t, b) in enumerate(chapters, 1):
        print(f"  {i:02d}. {t}  ({len(clean_for_speech(b)):,} chars)")

    if a.text_only:
        print(f"\nReview/edit {md_path.name}, then rerun without --text-only.")
        return
    narrate(chapters, out_dir, a.voice, a.speed)
    print(f"\nDone -> {out_dir}")


if __name__ == "__main__":
    main()

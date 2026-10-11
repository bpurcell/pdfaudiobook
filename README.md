# pdfaudiobook

Turn a PDF book into a chaptered MP3 audiobook, free and fully local.

**Pipeline:** PDF → [Marker](https://github.com/datalab-to/marker) (clean Markdown: strips headers, footers, page numbers, rejoins hyphenation) → chapter split → [Kokoro](https://github.com/hexgrad/kokoro) TTS (82M-param open model, Apache 2.0) → one MP3 per chapter.

## Setup (macOS)

```bash
brew install ffmpeg espeak-ng llama.cpp
python3.12 -m venv venv && source venv/bin/activate   # Kokoro needs Python ≤3.12
pip install -r requirements.txt
```

## Usage

```bash
# 1. Extract + clean text, preview the chapter list
python pdf2audiobook.py book.pdf --text-only

# 2. (Optional) edit book.md to remove anything you don't want read aloud

# 3. Narrate — reuses book.md, resumes if interrupted
python pdf2audiobook.py book.pdf
```

Output: `book_audio/01_Chapter_Name.mp3`, `02_...`, etc.

## Options

| Flag | Default | Notes |
|---|---|---|
| `--voice` | `af_heart` | Also `am_michael`, `bf_emma`, `bm_george` |
| `--speed` | `1.0` | Speech rate |
| `--heading-level` | `2` | Split at headings this deep; try `1` or `3` if chapters look wrong |
| `--min-chars` | `1500` | Shorter sections fold into the previous chapter |
| `--out` | `<book>_audio` | Output folder |
| `--force-extract` | off | Re-run Marker even if `book.md` exists |

## Notes

- Marker is the slow step (roughly an hour+ for a long book on a laptop CPU) and downloads ~2 GB of models on first run. It only runs once per book.
- If you can get an EPUB, it's cleaner than any PDF.
- Books, extracted text, and audio are git-ignored.

# FVTT Journal to PDF

A standalone Windows tool that converts **Foundry VTT Compendium Exporter
JournalEntry JSON files** into clean, readable PDFs.

This tool is designed for GMs who want to:
- Share rules, setting lore, or player guides outside Foundry
- Select only specific sections or headings
- Generate PDFs with a clickable Table of Contents

An `.exe` is provided for convenience, and full source code is included so
users can review or build it themselves.

---

## ✨ Features

- Opens JournalEntry JSON files exported via **Compendium Exporter**
  or from individual Journals (JSON formatted).
- Displays pages and headings in a checkbox tree
- Export full pages or individual sections (Must check what you want)
- Clean PDF output:
  - Clickable Table of Contents
  - Internal navigation links
  - Proper table rendering
- Removes Foundry-specific markup (UUIDs, embeds, UI cruft)

- 

---<img width="902" height="682" alt="Screenshot" src="https://github.com/user-attachments/assets/c07506d1-59ac-4bab-ac91-5032a2017a1c" />


## 📦 Downloads

This release includes **two downloads**:

### 1. Windows Executable
- `FVTT-Journal-to-PDF.exe`
- No Python required
- Provided for convenience
https://github.com/Gacky2k/fvtt-journal-to-pdf/releases/tag/v1.0.0

### 2. Source Code
- Full Python source included
- Build the EXE yourself if preferred

---

## 🔐 Security / Trust Note

If you are cautious about running executables from the internet (which is
reasonable), you can:
1. Download the **source zip**
2. Review all code
3. Build the EXE yourself using the instructions below

The provided EXE is built directly from the included source.

---

## ▶️ Running from Source

### Requirements
- Windows
- Python 3.11+ (https://www.python.org)

### Setup
```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py




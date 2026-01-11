"""Extract equipment info from PDF spec sheets."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import fitz  # PyMuPDF
from pathlib import Path

sys.path.insert(0, '.')
from core import database

PDF_FOLDER = Path(r"C:\Users\tomad\Downloads\machine sheet-20260102T131623Z-1-001\machine sheet")

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF file."""
    try:
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()
    except Exception as e:
        print(f"  Error reading PDF: {e}")
        return ""

def main():
    pdf_files = list(PDF_FOLDER.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files\n")

    for pdf_path in pdf_files:
        print(f"=== {pdf_path.name} ===")
        text = extract_text_from_pdf(pdf_path)

        if text:
            # Show first 500 chars of extracted text
            preview = text[:800].replace('\n', ' ')
            print(f"Text preview: {preview}...")
            print()
        else:
            print("  No text extracted")
            print()

if __name__ == "__main__":
    main()

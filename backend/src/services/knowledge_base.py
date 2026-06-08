import hashlib
from pathlib import Path

from pypdf import PdfReader


class KnowledgeBase:
    MIN_EXTRACTED_TEXT_LENGTH = 10

    def __init__(self, upload_dir: str):
        self.upload_dir = Path(upload_dir)

    def save_pdf(self, paper_id: str, filename: str, content: bytes) -> str:
        paper_dir = self.upload_dir / self._safe_segment(paper_id)
        paper_dir.mkdir(parents=True, exist_ok=True)

        safe_filename = self._safe_filename(filename)
        pdf_path = paper_dir / safe_filename
        pdf_path.write_bytes(content)
        return str(pdf_path)

    def extract_text(self, pdf_path: str) -> str:
        try:
            reader = PdfReader(pdf_path)
        except Exception as exc:
            raise ValueError(f"failed to extract text from pdf: {pdf_path}") from exc

        parts = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            cleaned = " ".join(page_text.split())
            if cleaned:
                parts.append(cleaned)

        text = "\n".join(parts).strip()
        if len(text) < self.MIN_EXTRACTED_TEXT_LENGTH:
            raise ValueError(f"extracted text is empty or too short: {pdf_path}")

        return text

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> list[dict]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        chunks = []
        step = chunk_size - overlap
        chunk_index = 0

        for start in range(0, len(text), step):
            chunk_text = text[start : start + chunk_size].strip()
            if not chunk_text:
                continue

            chunks.append(
                {
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                    "chunk_hash": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                    "vector_ref": None,
                }
            )
            chunk_index += 1

            if start + chunk_size >= len(text):
                break

        return chunks

    @staticmethod
    def _safe_segment(value: str) -> str:
        safe = "_".join(value.strip().split())
        safe = safe.replace("/", "_").replace("\\", "_")
        return safe or "unknown"

    @classmethod
    def _safe_filename(cls, filename: str) -> str:
        name = Path(filename).name
        safe = cls._safe_segment(name)
        if not safe.lower().endswith(".pdf"):
            safe = f"{safe}.pdf"
        return safe

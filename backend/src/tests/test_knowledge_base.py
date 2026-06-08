from pathlib import Path

import pytest

from services.knowledge_base import KnowledgeBase


def make_text_pdf_bytes(text: str) -> bytes:
    encoded = text.encode("latin-1")
    stream = (
        b"BT\n"
        b"/F1 24 Tf\n"
        b"100 100 Td\n"
        b"(" + encoded + b") Tj\n"
        b"ET\n"
    )
    length = len(stream)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Type /Catalog /Pages 2 0 R >>\n"
        b"endobj\n"
        b"2 0 obj\n"
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n"
        b"endobj\n"
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
        b"endobj\n"
        + f"4 0 obj\n<< /Length {length} >>\nstream\n".encode("ascii")
        + stream
        + b"endstream\nendobj\n"
        b"5 0 obj\n"
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
        b"endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000010 00000 n \n"
        b"0000000063 00000 n \n"
        b"0000000122 00000 n \n"
        b"0000000248 00000 n \n"
        b"0000000354 00000 n \n"
        b"trailer\n"
        b"<< /Root 1 0 R /Size 6 >>\n"
        b"startxref\n"
        b"424\n"
        b"%%EOF\n"
    )


def test_save_pdf_writes_bytes_under_upload_dir(tmp_path):
    kb = KnowledgeBase(upload_dir=str(tmp_path / "uploads"))

    pdf_path = kb.save_pdf(
        paper_id="paper-1",
        filename="../unsafe name.pdf",
        content=b"%PDF-1.4 fake pdf",
    )

    saved_path = Path(pdf_path)
    assert saved_path.exists()
    assert saved_path.parent == tmp_path / "uploads" / "paper-1"
    assert saved_path.name == "unsafe_name.pdf"
    assert saved_path.read_bytes() == b"%PDF-1.4 fake pdf"


def test_extract_text_returns_text_for_supported_pdf_fixture(tmp_path):
    kb = KnowledgeBase(upload_dir=str(tmp_path / "uploads"))
    pdf_path = tmp_path / "fixture.pdf"
    pdf_path.write_bytes(make_text_pdf_bytes("Hello Phase 2C"))

    extracted = kb.extract_text(str(pdf_path))

    assert "Hello Phase 2C" in extracted


def test_extract_text_fails_clearly_for_invalid_pdf(tmp_path):
    kb = KnowledgeBase(upload_dir=str(tmp_path / "uploads"))
    pdf_path = tmp_path / "invalid.pdf"
    pdf_path.write_bytes(b"not a real pdf")

    with pytest.raises(ValueError, match="failed to extract text"):
        kb.extract_text(str(pdf_path))


def test_extract_text_treats_empty_extracted_text_as_failure(tmp_path, monkeypatch):
    kb = KnowledgeBase(upload_dir=str(tmp_path / "uploads"))
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    class FakePage:
        def extract_text(self) -> str:
            return "   \n\n   "

    class FakeReader:
        def __init__(self, _: str):
            self.pages = [FakePage()]

    monkeypatch.setattr("services.knowledge_base.PdfReader", FakeReader)

    with pytest.raises(ValueError, match="extracted text is empty"):
        kb.extract_text(str(pdf_path))


def test_chunk_text_is_deterministic_and_preserves_overlap(tmp_path):
    kb = KnowledgeBase(upload_dir=str(tmp_path / "uploads"))
    text = "abcdefghij"

    chunks = kb.chunk_text(text, chunk_size=4, overlap=1)

    assert [chunk["chunk_index"] for chunk in chunks] == [0, 1, 2]
    assert [chunk["text"] for chunk in chunks] == ["abcd", "defg", "ghij"]
    assert chunks[0]["chunk_hash"] == kb.chunk_text(text, chunk_size=4, overlap=1)[0]["chunk_hash"]


def test_chunk_text_ignores_blank_chunks(tmp_path):
    kb = KnowledgeBase(upload_dir=str(tmp_path / "uploads"))

    chunks = kb.chunk_text("abc   ", chunk_size=3, overlap=0)

    assert [chunk["text"] for chunk in chunks] == ["abc"]

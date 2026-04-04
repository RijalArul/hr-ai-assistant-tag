from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader

from app.models import AttachmentInput, EvidenceItem, FileAgentResult
from app.services.gemini import extract_file_with_gemini

TEXT_FILE_SUFFIXES = {".txt", ".md", ".json", ".csv", ".log"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
GEMINI_FIRST_SUFFIXES = {".pdf", *IMAGE_SUFFIXES}


def _read_pdf_text(path: Path) -> tuple[str | None, dict[str, Any]]:
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages[:5]:
        extracted = page.extract_text()
        if extracted:
            pages.append(extracted.strip())
    return (
        "\n".join(page for page in pages if page).strip() or None,
        {
            "page_count": len(reader.pages),
        },
    )


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _inspect_image(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        return {
            "format": image.format,
            "width": image.width,
            "height": image.height,
        }


async def run_file_agent(attachments: list[AttachmentInput]) -> FileAgentResult:
    details: list[dict[str, Any]] = []
    evidence: list[EvidenceItem] = []
    extracted_segments: list[str] = []

    for attachment in attachments:
        detail: dict[str, Any] = {
            "file_name": attachment.resolved_name,
            "content_type": attachment.content_type,
            "file_path": attachment.file_path,
            "status": "processed",
        }
        extracted_text: str | None = None

        if attachment.inline_text:
            extracted_text = attachment.inline_text.strip()
            detail["source"] = "inline_text"
            detail["text_length"] = len(extracted_text)
        elif attachment.file_path:
            path = Path(attachment.file_path).expanduser().resolve()
            detail["resolved_path"] = str(path)
            try:
                if not path.exists():
                    detail["status"] = "error"
                    detail["error"] = "File not found."
                elif attachment.suffix in GEMINI_FIRST_SUFFIXES:
                    gemini_result = await extract_file_with_gemini(path)
                    gemini_text = gemini_result.text
                    if gemini_result.is_success and isinstance(gemini_text, str):
                        extracted_text = gemini_text
                        detail["source"] = "gemini"
                        detail["text_length"] = len(extracted_text)
                    elif attachment.suffix == ".pdf":
                        extracted_text, pdf_metadata = _read_pdf_text(path)
                        detail["source"] = "pdf"
                        detail.update(pdf_metadata)
                        detail["note"] = (
                            "Gemini tidak tersedia atau gagal, jadi file dibaca "
                            "dengan extractor PDF lokal. "
                            f"Alasan fallback: {gemini_result.fallback_reason or '-'}"
                        )
                    else:
                        detail["source"] = "image_metadata"
                        detail.update(_inspect_image(path))
                        detail["note"] = (
                            "Gemini tidak tersedia atau gagal, jadi image hanya "
                            "dibaca pada level metadata. "
                            f"Alasan fallback: {gemini_result.fallback_reason or '-'}"
                        )
                elif attachment.suffix == ".pdf":
                    extracted_text, pdf_metadata = _read_pdf_text(path)
                    detail["source"] = "pdf"
                    detail.update(pdf_metadata)
                elif attachment.suffix in TEXT_FILE_SUFFIXES:
                    extracted_text = _read_text_file(path)
                    detail["source"] = "text_file"
                    detail["text_length"] = len(extracted_text)
                elif attachment.suffix in IMAGE_SUFFIXES:
                    detail["source"] = "image_metadata"
                    detail.update(_inspect_image(path))
                    detail["note"] = (
                        "Image metadata berhasil dibaca, tetapi OCR belum dijalankan "
                        "tanpa provider ekstraksi visual."
                    )
                else:
                    detail["status"] = "fallback"
                    detail["note"] = "Jenis lampiran belum didukung untuk ekstraksi lokal."
            except Exception as exc:
                detail["status"] = "error"
                detail["error"] = str(exc)
        else:
            detail["status"] = "fallback"
            detail["note"] = "Lampiran tidak punya sumber konten yang bisa diproses."

        if extracted_text:
            extracted_segments.append(f"[{attachment.resolved_name}]\n{extracted_text}")
            detail["extracted_preview"] = extracted_text[:280]
            evidence.append(
                EvidenceItem(
                    source_type="file",
                    title=attachment.resolved_name,
                    snippet=extracted_text[:240],
                    metadata={
                        "status": detail["status"],
                        "source": detail.get("source"),
                    },
                )
            )
        else:
            evidence.append(
                EvidenceItem(
                    source_type="file",
                    title=attachment.resolved_name,
                    snippet=detail.get("note"),
                    metadata={
                        "status": detail["status"],
                        "source": detail.get("source"),
                    },
                )
            )

        details.append(detail)

    extracted_text = "\n\n".join(segment for segment in extracted_segments if segment) or None
    if extracted_text:
        summary = (
            f"File-agent memproses {len(attachments)} lampiran dan berhasil "
            f"mengekstrak teks dari {len(extracted_segments)} lampiran."
        )
    else:
        summary = (
            f"File-agent memproses {len(attachments)} lampiran, tetapi belum ada "
            "teks yang bisa diekstrak secara lokal."
        )

    return FileAgentResult(
        attachments_processed=len(attachments),
        summary=summary,
        extracted_text=extracted_text,
        attachments=details,
        evidence=evidence,
    )

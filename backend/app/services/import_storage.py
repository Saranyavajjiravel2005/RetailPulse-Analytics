import os
import io
import csv
from pathlib import Path
from uuid import UUID
from fastapi import UploadFile, HTTPException, status
import logging

logger = logging.getLogger("retailpulse")

UPLOAD_DIR = Path("uploads/imports")
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB

# Known binary signatures to reject immediately
BINARY_SIGNATURES = [
    b"\x7fELF",              # Linux executable
    b"MZ",                   # DOS/Windows PE executable
    b"PK\x03\x04",           # ZIP / Office archive
    b"%PDF",                 # PDF document
    b"\x89PNG",              # PNG image
    b"\xff\xd8\xff",         # JPEG image
    b"GIF8",                 # GIF image
    b"\x1f\x8b",             # GZIP archive
    b"\x42\x5a\x68",         # BZIP2
    b"\x52\x61\x72\x21",     # RAR
    b"\x00\x00\x01\x00",     # Windows Icon
]


def ensure_upload_dir(company_id: UUID) -> Path:
    target_dir = UPLOAD_DIR / str(company_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def get_import_file_path(company_id: UUID, import_id: UUID) -> Path:
    return UPLOAD_DIR / str(company_id) / f"{import_id}.csv"


def validate_csv_content(content: bytes, filename: str) -> str:
    """
    Validate that the file content is genuinely CSV/text and not binary, malformed, or dangerous.
    Returns the decoded text string.
    """
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is completely empty."
        )

    # Check for binary signatures
    for sig in BINARY_SIGNATURES:
        if content.startswith(sig):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file content: '{filename}' appears to be a binary file, not a CSV."
            )

    # Check for null bytes (binary indicator)
    if b"\x00" in content[:4096]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format: Binary null bytes detected in CSV file."
        )

    # Try decoding
    text = None
    for enc in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to decode file as valid text (UTF-8 or Latin-1 required)."
        )

    # Check for basic delimited structure
    first_lines = [line.strip() for line in text.splitlines() if line.strip()][:5]
    if not first_lines:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file contains no readable text rows."
        )

    # Ensure header has at least one common delimiter
    sample = first_lines[0]
    has_delimiter = any(d in sample for d in [",", ";", "\t", "|"])
    if not has_delimiter and len(first_lines) > 1:
        # Check second line
        has_delimiter = any(d in first_lines[1] for d in [",", ";", "\t", "|"])

    if not has_delimiter:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File structure is not a valid CSV. No recognized delimiter (comma, semicolon, tab, pipe) detected."
        )

    return text


async def save_uploaded_import_file(company_id: UUID, import_id: UUID, file: UploadFile) -> tuple[Path, bytes]:
    """
    Validates file size and content, saves to disk persistently, and returns the path and bytes.
    """
    ensure_upload_dir(company_id)
    target_path = get_import_file_path(company_id, import_id)

    # Read content with 50MB limit check
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds the 50MB limit (uploaded: {len(content) / (1024*1024):.2f}MB)."
        )

    # Content validation
    validate_csv_content(content, file.filename or "unknown.csv")

    # Write persistently to disk
    with open(target_path, "wb") as f:
        f.write(content)

    logger.info(f"Persisted import file for company {company_id}, import {import_id} to {target_path}")
    return target_path, content


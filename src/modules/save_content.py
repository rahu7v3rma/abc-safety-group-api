import uuid
from typing import List

import aiofiles
from fastapi import UploadFile

from src import log

TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",  # noqa: E501
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",  # noqa: E501
    "application/msword": "doc",
    "application/vnd.ms-powerpoint": "ppt",
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpg",
    "text/csv": "csv",
}


async def save_content(
    types: str,
    file: UploadFile,
    content_types: List[str],
) -> dict:
    """Function to save any sort of content to folder

    Args:
        types (str, optional): Whether its a pdf, image, etc..
        Defaults to None.
        file_str (str, optional): Nulled out now i believe. Defaults to None.
        content_types (List[str], optional): File type, PNG/JPEG, etc.
        Defaults to None.

    Returns:
        Tuple[bool, str]: True with message if image saved, false with message
        if not
    """

    file_id = str(uuid.uuid4())

    if not types:
        return {
            "success": False,
            "reason": "Type needs to be provided",
        }

    try:
        format = file.content_type
        if format not in content_types:
            log.error(f" FAILED Content type: {format}")
            return {
                "success": False,
                "reason": "Non supported file type.",
            }

        format = TYPES[format] if TYPES.get(format) else format

        file_path = f"/source/src/content/{types}/{file_id}.{format}"
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(await file.read())

        return {
            "success": True,
            "file_name": file.filename,
            "file_id": f"{file_id}.{format}",
        }

    except Exception:
        log.exception("Failed to save file")

    return {
        "success": False,
        "reason": "Failed to save file",
    }

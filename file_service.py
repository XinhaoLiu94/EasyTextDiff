"""Strict text decoding and atomic document saves, without UI dependencies.

Mixed endings are tracked on load. Saving an unchanged document preserves its
original bytes exactly. After an edit, its recorded predominant newline style
is used; callers can inspect ``mixed_newlines`` before asking the user to save.
"""

from __future__ import annotations

import codecs
import os
from pathlib import Path
import re
import tempfile

from models import DocumentModel, Newline


DEFAULT_MAX_BYTES = 4 * 1024 * 1024


class FileServiceError(Exception):
    pass


class UnsupportedEncodingError(FileServiceError):
    pass


class BinaryFileError(FileServiceError):
    pass


class FileTooLargeError(FileServiceError):
    pass


class ExternalModificationError(FileServiceError):
    pass


def _newline_metadata(text: str) -> tuple[Newline, bool, dict[str, int]]:
    endings = re.findall(r"\r\n|\r|\n", text)
    counts = {ending.value: 0 for ending in Newline}
    for ending in endings:
        counts[ending] += 1
    if not endings:
        return Newline.LF, False, counts
    # A tie uses the first encountered convention, making the rule predictable.
    predominant = max(dict.fromkeys(endings), key=lambda ending: counts[ending])
    return Newline(predominant), sum(count > 0 for count in counts.values()) > 1, counts


def _reject_binary(text: str) -> None:
    controls = sum(ord(character) < 32 and character not in "\t\n\r\f\x1b"
                   for character in text)
    if "\x00" in text or (text and controls / len(text) > 0.01):
        raise BinaryFileError("文件包含二进制数据，无法作为文本打开。")


def _decode(raw: bytes) -> tuple[str, str, bytes]:
    if raw.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        raise UnsupportedEncodingError("暂不支持 UTF-32，请先转换为 UTF-8 或 UTF-16。")
    for bom, encoding in ((codecs.BOM_UTF8, "utf-8"),
                          (codecs.BOM_UTF16_LE, "utf-16-le"),
                          (codecs.BOM_UTF16_BE, "utf-16-be")):
        if raw.startswith(bom):
            try:
                text = raw[len(bom):].decode(encoding, errors="strict")
            except UnicodeDecodeError as error:
                raise UnsupportedEncodingError("文件编码与 BOM 不匹配或内容不完整。") from error
            _reject_binary(text)
            return text, encoding, bom
    if b"\x00" in raw:
        raise BinaryFileError("文件包含空字节；二进制文件或无 BOM 的 UTF-16 无法自动识别。")
    for encoding in ("utf-8", "gb18030"):
        try:
            text = raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue
        _reject_binary(text)
        return text, encoding, b""
    raise UnsupportedEncodingError("文件不是有效的 UTF-8、UTF-16 BOM 或 GB18030 文本。")


def read_document(path: str | Path, max_bytes: int = DEFAULT_MAX_BYTES) -> DocumentModel:
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive.")
    target = Path(path).expanduser().resolve()
    try:
        if target.stat().st_size > max_bytes:
            raise FileTooLargeError(f"文件超过 {max_bytes} 字节的大小限制。")
        with target.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
    except OSError as error:
        raise FileServiceError(f"无法读取文件：{target}\n{error}") from error
    if len(raw) > max_bytes:
        raise FileTooLargeError(f"文件超过 {max_bytes} 字节的大小限制。")
    text, encoding, bom = _decode(raw)
    newline, mixed, counts = _newline_metadata(text)
    document = DocumentModel(text, target, encoding, newline, bom, mixed, counts)
    document.mark_saved(original_bytes=raw)
    return document


def _encoding_plan(document: DocumentModel, encoding: str | None) -> tuple[str, bytes]:
    requested = document.encoding if encoding is None else encoding
    try:
        key = codecs.lookup(requested).name
    except (LookupError, TypeError) as error:
        raise UnsupportedEncodingError(f"不支持的文本编码：{requested}") from error
    if key == "utf-8-sig":
        return "utf-8", codecs.BOM_UTF8
    if key == "utf-16":
        return "utf-16-le", codecs.BOM_UTF16_LE
    expected_boms = {"utf-8": codecs.BOM_UTF8, "utf-16-le": codecs.BOM_UTF16_LE,
                     "utf-16-be": codecs.BOM_UTF16_BE, "gb18030": b""}
    if key not in expected_boms:
        raise UnsupportedEncodingError(f"不支持的文本编码：{requested}")
    if encoding is None:
        if document.bom not in (b"", expected_boms[key]):
            raise UnsupportedEncodingError("BOM 与所选编码不匹配。")
        return key, document.bom
    # Explicit UTF-8 means no BOM; explicit UTF-16 choices include their BOM.
    return key, expected_boms[key] if key.startswith("utf-16-") else b""


def _check_external_changes(target: Path, expected_bytes: bytes) -> None:
    try:
        with target.open("rb") as stream:
            # Reading one extra byte detects growth without loading an arbitrary
            # replacement file into memory.
            current = stream.read(len(expected_bytes) + 1)
    except OSError as error:
        raise ExternalModificationError(
            "磁盘上的文件已移除或无法验证；请重新打开，或确认后覆盖保存。") from error
    if current != expected_bytes:
        raise ExternalModificationError(
            "磁盘上的文件已被其他程序修改；请重新打开，或确认后覆盖保存。")


def _atomic_write(target: Path, payload: bytes, expected_bytes: bytes | None = None) -> None:
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".easytextdiff-", suffix=".tmp",
                                                dir=target.parent)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if expected_bytes is not None:
            _check_external_changes(target, expected_bytes)
        os.replace(temporary, target)
        temporary = None
    except OSError as error:
        raise FileServiceError(f"无法保存文件：{target}\n{error}") from error
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def save_document(document: DocumentModel, path: str | Path | None = None, *,
                  encoding: str | None = None,
                  newline: Newline | str | None = None,
                  overwrite_external: bool = False) -> DocumentModel:
    """Save atomically, committing model state only after a successful replace.

    Explicit ``utf-8`` strips the BOM; ``utf-8-sig`` adds it. Explicit UTF-16 LE
    or BE adds the matching BOM. Omitting encoding preserves the current BOM.
    Unrepresentable characters raise instead of being replaced or discarded.
    Same-path saves reject changed/missing disk contents unless the caller
    explicitly passes ``overwrite_external=True`` after obtaining confirmation.
    """
    selected_path = document.path if path is None else Path(path)
    if selected_path is None:
        raise FileServiceError("请先选择保存路径。")
    target = Path(selected_path).expanduser().resolve()
    target_encoding, target_bom = _encoding_plan(document, encoding)
    try:
        target_newline = Newline(document.newline if newline is None else newline)
    except ValueError as error:
        raise FileServiceError("不支持的换行格式。") from error
    reuse_original = (not document.modified and document._original_bytes is not None
                      and target_encoding == document.encoding
                      and target_newline == document.newline and target_bom == document.bom)
    if reuse_original:
        payload = document._original_bytes
        mixed, counts = document.mixed_newlines, document.newline_counts.copy()
    else:
        rendered = document.text.replace("\n", target_newline.value)
        try:
            payload = target_bom + rendered.encode(target_encoding, errors="strict")
        except UnicodeEncodeError as error:
            raise UnsupportedEncodingError(
                f"文本包含 {target_encoding} 无法表示的字符；原文件未更改。") from error
        _, mixed, counts = _newline_metadata(rendered)
    expected_bytes = None
    if (not overwrite_external and document.path is not None
            and target == Path(document.path).expanduser().resolve()):
        expected_bytes = document._original_bytes
    _atomic_write(target, payload, expected_bytes)
    document.path = target
    document.encoding = target_encoding
    document.newline = target_newline
    document.bom = target_bom
    document.mixed_newlines = mixed
    document.newline_counts = counts
    document.mark_saved(original_bytes=payload)
    return document

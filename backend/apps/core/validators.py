"""Upload validators: size, extension, real content type (via Pillow), filename and image dimensions."""
import os
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from PIL import Image, UnidentifiedImageError

_SAFE_NAME = re.compile(r"^[\w\-. ]{1,200}$")


def validate_safe_filename(file):
    raw = (getattr(file, "name", "") or "").replace("\\", "/")
    name = raw.rsplit("/", 1)[-1]
    if not name or ".." in name or not _SAFE_NAME.match(name):
        raise ValidationError("File name is missing or contains unsupported characters.")


@deconstructible
class FileSizeValidator:
    def __init__(self, max_bytes):
        self.max_bytes = max_bytes

    def __call__(self, file):
        if file.size > self.max_bytes:
            raise ValidationError(f"File is too large. Maximum size is {self.max_bytes // (1024 * 1024)} MB.")

    def __eq__(self, other):
        return isinstance(other, FileSizeValidator) and other.max_bytes == self.max_bytes


@deconstructible
class ImageFileValidator:
    """
    Validates an uploaded image by decoding it, not by trusting the extension or
    the client-supplied Content-Type.
    """

    FORMAT_EXTENSIONS = {"JPEG": {".jpg", ".jpeg"}, "PNG": {".png"}, "WEBP": {".webp"}}

    def __init__(self, max_bytes=None, max_width=4096, max_height=4096, min_width=16, min_height=16,
                 allowed_formats=("JPEG", "PNG", "WEBP")):
        self.max_bytes = max_bytes
        self.max_width = max_width
        self.max_height = max_height
        self.min_width = min_width
        self.min_height = min_height
        self.allowed_formats = tuple(allowed_formats)

    def __call__(self, file):
        max_bytes = self.max_bytes or settings.MAX_IMAGE_UPLOAD_BYTES
        FileSizeValidator(max_bytes)(file)
        validate_safe_filename(file)

        ext = os.path.splitext(file.name)[1].lower()
        allowed_exts = set().union(*(self.FORMAT_EXTENSIONS[f] for f in self.allowed_formats))
        if ext not in allowed_exts:
            raise ValidationError(f"Unsupported file extension. Allowed: {', '.join(sorted(allowed_exts))}.")

        try:
            file.seek(0)
            with Image.open(file) as img:
                image_format = img.format
                width, height = img.size
                img.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValidationError("Upload a valid image.") from exc
        finally:
            file.seek(0)

        if image_format not in self.allowed_formats:
            raise ValidationError(f"Unsupported image type. Allowed: {', '.join(self.allowed_formats)}.")
        if ext not in self.FORMAT_EXTENSIONS[image_format]:
            raise ValidationError("File extension does not match the image content.")
        if width > self.max_width or height > self.max_height:
            raise ValidationError(f"Image is too large. Maximum is {self.max_width}x{self.max_height}px.")
        if width < self.min_width or height < self.min_height:
            raise ValidationError(f"Image is too small. Minimum is {self.min_width}x{self.min_height}px.")

    def __eq__(self, other):
        return isinstance(other, ImageFileValidator) and self.__dict__ == other.__dict__


@deconstructible
class DocumentFileValidator:
    """PDFs (checked by magic bytes) or images (decoded by Pillow)."""

    def __init__(self, max_bytes=10 * 1024 * 1024):
        self.max_bytes = max_bytes

    def __call__(self, file):
        FileSizeValidator(self.max_bytes)(file)
        validate_safe_filename(file)
        ext = os.path.splitext(file.name)[1].lower()
        if ext == ".pdf":
            file.seek(0)
            header = file.read(5)
            file.seek(0)
            if header != b"%PDF-":
                raise ValidationError("Upload a valid PDF document.")
            return
        if ext in {".jpg", ".jpeg", ".png", ".webp"}:
            ImageFileValidator(max_bytes=self.max_bytes, max_width=8000, max_height=8000)(file)
            return
        raise ValidationError("Unsupported file type. Allowed: PDF, JPG, PNG, WEBP.")

    def __eq__(self, other):
        return isinstance(other, DocumentFileValidator) and other.max_bytes == self.max_bytes


phone_validator_regex = r"^\+?[0-9]{7,15}$"

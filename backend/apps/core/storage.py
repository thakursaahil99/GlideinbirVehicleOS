"""
Storage abstraction.

Models never instantiate a storage backend directly; they use ``media_storage``
(resolved from ``settings.STORAGES['default']``). Local filesystem in
development, S3-compatible storage in production via ``USE_S3_STORAGE``.
"""
import os
import uuid

from django.core.files.storage import storages
from django.utils import timezone
from django.utils.deconstruct import deconstructible


def media_storage():
    return storages["default"]


@deconstructible
class UploadPath:
    """Builds ``<prefix>/<yyyy>/<mm>/<uuid><ext>`` so client file names never reach the filesystem."""

    def __init__(self, prefix):
        self.prefix = prefix.strip("/")

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename)[1].lower()[:10]
        now = timezone.now()
        return f"{self.prefix}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{ext}"

    def __eq__(self, other):
        return isinstance(other, UploadPath) and other.prefix == self.prefix

"""Evidence image handling. Phone photos carry GPS in EXIF: it is always stripped."""

import hashlib
import io

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# Guards against decompression bombs even before the pixel check below.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def sanitize_image(content: bytes) -> tuple[bytes, str]:
    """Validate that bytes are a real image and re-encode it without metadata.

    Returns (jpeg_bytes, sha256 of the sanitized bytes). Re-encoding drops EXIF (including
    GPS), ICC oddities and anything appended to the file, and normalizes the format.
    """
    if not content or len(content) > MAX_BYTES:
        raise ValidationError("Imagem vazia ou maior que 8 MB.")
    try:
        with Image.open(io.BytesIO(content)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise ValidationError("Formato de imagem não suportado (use JPEG, PNG ou WEBP).")
            width, height = probe.size
            if width * height > MAX_PIXELS:
                raise ValidationError("Imagem com resolução excessiva.")
            probe.load()
            image = probe.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError("Arquivo não é uma imagem válida.") from exc
    clean = io.BytesIO()
    image.save(clean, format="JPEG", quality=85, optimize=True)  # no exif= argument: none kept
    data = clean.getvalue()
    return data, hashlib.sha256(data).hexdigest()

"""Validate an uploaded image by actually decoding it, and re-encode a bounded JPEG for the model."""

from io import BytesIO

from PIL import Image, UnidentifiedImageError

from ..config import ALLOWED_IMAGE_FORMATS, MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, MODEL_IMAGE_EDGE

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class ImageError(Exception):
    """Rejection reason that is safe to show to the user."""


def prepare_image(data: bytes) -> bytes:
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageError("圖片超過 8 MB，請縮小後重傳。")
    try:
        with Image.open(BytesIO(data)) as img:
            if img.format not in ALLOWED_IMAGE_FORMATS:
                raise ImageError("只支援 PNG、JPEG、WebP、GIF 圖片。")
            if img.width * img.height > MAX_IMAGE_PIXELS:
                raise ImageError("圖片尺寸過大（上限約 1600 萬像素），請縮小後重傳。")
            img.seek(0)
            rgb = img.convert("RGB")
    except ImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ImageError("這個檔案無法當作圖片開啟，請換一張照片。") from None
    rgb.thumbnail((MODEL_IMAGE_EDGE, MODEL_IMAGE_EDGE))
    out = BytesIO()
    rgb.save(out, format="JPEG", quality=88)
    return out.getvalue()

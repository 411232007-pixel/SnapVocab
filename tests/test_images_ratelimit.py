from io import BytesIO

import pytest
from PIL import Image

from snapvocab.config import MAX_IMAGE_BYTES
from snapvocab.services.images import ImageError, prepare_image
from snapvocab.services.ratelimit import RateLimiter


def _img(fmt: str, size=(100, 80)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, "red").save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "GIF"])
def test_supported_formats_become_jpeg(fmt):
    out = prepare_image(_img(fmt))
    assert Image.open(BytesIO(out)).format == "JPEG"


def test_large_image_is_downscaled():
    out = prepare_image(_img("PNG", (3000, 2000)))
    assert max(Image.open(BytesIO(out)).size) <= 1568


def test_non_image_rejected():
    with pytest.raises(ImageError):
        prepare_image(b"not an image at all")


def test_unsupported_format_rejected():
    with pytest.raises(ImageError):
        prepare_image(_img("BMP"))


def test_too_many_pixels_rejected():
    with pytest.raises(ImageError):
        prepare_image(_img("PNG", (4001, 4000)))


def test_too_many_bytes_rejected():
    with pytest.raises(ImageError):
        prepare_image(b"0" * (MAX_IMAGE_BYTES + 1))


def test_rate_limiter_window():
    now = [0.0]
    rl = RateLimiter(2, 10.0, clock=lambda: now[0])
    assert rl.try_acquire("a") == 0
    assert rl.try_acquire("a") == 0
    assert rl.try_acquire("a") > 0
    assert rl.try_acquire("b") == 0  # separate per user
    now[0] = 10.5
    assert rl.try_acquire("a") == 0

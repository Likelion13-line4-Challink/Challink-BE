import hashlib
from PIL import Image
import imagehash

def calc_sha1(django_file) -> str:
    pos = django_file.tell() if hasattr(django_file, "tell") else None
    try:
        django_file.seek(0)
        h = hashlib.sha1()
        for chunk in iter(lambda: django_file.read(8192), b""):
            h.update(chunk)
        return h.hexdigest()
    finally:
        try:
            django_file.seek(pos or 0)
        except Exception:
            pass

def calc_phash(django_file) -> int:
    pos = django_file.tell() if hasattr(django_file, "tell") else None
    try:
        django_file.seek(0)
        img = Image.open(django_file).convert("RGB")
        ph = imagehash.phash(img)  # 64-bit
        return int(str(ph), 16)
    finally:
        try:
            django_file.seek(pos or 0)
        except Exception:
            pass

def hamming_distance64(a: int, b: int) -> int:
    return (a ^ b).bit_count()

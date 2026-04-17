import PyInstaller.__main__
import os
from pathlib import Path

print("--- Starting Build Process for InDoc-CLI ---")


def _png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid PNG signature")
    if len(png_bytes) < 24:
        raise ValueError("PNG file too small")
    width = int.from_bytes(png_bytes[16:20], "big")
    height = int.from_bytes(png_bytes[20:24], "big")
    return width, height


def _wrap_png_as_ico(png_path: Path, ico_path: Path) -> None:
    png_bytes = png_path.read_bytes()
    w, h = _png_dimensions(png_bytes)
    if w != h:
        raise ValueError(f"Icon PNG must be square. Got {w}x{h}.")
    if w > 256:
        raise ValueError(f"Icon PNG must be <= 256x256 for ICO. Got {w}x{h}. Provide a 256x256 PNG.")
    size_byte = 0 if w == 256 else w
    # ICO header (reserved=0, type=1, count=1)
    header = (0).to_bytes(2, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
    # ICONDIRENTRY (16 bytes)
    # width, height, colorCount, reserved, planes, bitCount, bytesInRes, imageOffset
    entry = bytes([size_byte, size_byte, 0, 0])
    entry += (1).to_bytes(2, "little")  # planes
    entry += (32).to_bytes(2, "little")  # bitCount (nominal; PNG is embedded)
    entry += len(png_bytes).to_bytes(4, "little")
    entry += (6 + 16).to_bytes(4, "little")
    ico_bytes = header + entry + png_bytes
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    ico_path.write_bytes(ico_bytes)


repo_root = Path(__file__).resolve().parent
assets_dir = repo_root / "assets"
assets_dir.mkdir(parents=True, exist_ok=True)

jpg_icon = assets_dir / "Indoc Cli.jpg"
png_icon = assets_dir / "indoc-icon.png"
ico_icon = assets_dir / "indoc-icon.ico"
temp_dir = Path(os.environ.get("TEMP") or os.environ.get("TMP") or str(repo_root))
temp_icon = temp_dir / "InDoc-CLI.icon.ico"

dist_dir = repo_root / "dist"
build_dir = repo_root / "build"
spec_path = repo_root / "InDoc-CLI.spec"

if dist_dir.exists():
    for p in dist_dir.glob("*"):
        try:
            if p.is_dir():
                import shutil
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
        except Exception:
            pass
if build_dir.exists():
    try:
        import shutil
        shutil.rmtree(build_dir, ignore_errors=True)
    except Exception:
        pass
try:
    spec_path.unlink(missing_ok=True)
except Exception:
    pass

if not ico_icon.exists():
    if png_icon.exists():
        _wrap_png_as_ico(png_icon, ico_icon)
    elif jpg_icon.exists():
        try:
            from PIL import Image
            tmp_png = assets_dir / "indoc-icon.from-jpg.png"
            with Image.open(jpg_icon) as img:
                img = img.convert("RGBA")
                w, h = img.size
                if w != h:
                    raise ValueError(f"Icon image must be square. Got {w}x{h}.")
                if w > 256:
                    raise ValueError(f"Icon image must be <= 256x256 for ICO. Got {w}x{h}.")
                img.save(tmp_png, format="PNG")
            _wrap_png_as_ico(tmp_png, ico_icon)
            try:
                tmp_png.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception as e:
            raise FileNotFoundError(
                "Icon conversion failed. Provide assets/indoc-icon.ico or assets/indoc-icon.png "
                f"(or ensure Pillow is installed to convert assets/Indoc Cli.jpg). Details: {e}"
            ) from e
    else:
        raise FileNotFoundError(
            "Official icon missing. Place the provided icon at assets/Indoc Cli.jpg "
            "(or provide assets/indoc-icon.png / assets/indoc-icon.ico) and re-run the build."
        )

try:
    temp_icon.write_bytes(ico_icon.read_bytes())
except Exception as e:
    raise RuntimeError(f"Failed to stage icon into TEMP for PyInstaller: {e}") from e

PyInstaller.__main__.run([
    'main.py',
    '--onefile',
    '--name=InDoc-CLI',
    f'--icon={str(temp_icon)}',
    '--version-file=version_info.txt',
    '--clean'
])

print("\n--- Build Complete! Check 'dist/InDoc-CLI.exe' ---")

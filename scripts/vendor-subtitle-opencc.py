"""Reproduce the pinned private OpenCC dependency without installing into Python."""
import hashlib
import io
from pathlib import Path
import urllib.request
from zipfile import ZipFile

URL = "https://files.pythonhosted.org/packages/30/6b/055b7806f320cc8f2cdf23c5f70221c0dc1683fca9ffaf76dfc2ad4b91b6/opencc_python_reimplemented-0.1.7-py2.py3-none-any.whl"
SHA256 = "41b3b92943c7bed291f448e9c7fad4b577c8c2eae30fcfe5a74edf8818493aa6"
ROOT = Path(__file__).resolve().parents[1] / "cinecircuit_plugins/subtitle_manager/_vendor/opencc"


def main():
    content = urllib.request.urlopen(URL, timeout=60).read()
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise ValueError("OpenCC archive checksum mismatch")
    with ZipFile(io.BytesIO(content)) as archive:
        entries = {name.removeprefix("opencc/"): archive.read(name)
                   for name in archive.namelist() if name.startswith("opencc/") and not name.endswith("/")}
        entries["LICENSE.txt"] = archive.read("opencc_python_reimplemented-0.1.7.dist-info/LICENSE.txt")
        for name, data in entries.items():
            target = (ROOT / name).resolve()
            if ROOT.resolve() not in target.parents:
                raise ValueError("Invalid vendor path")
            if target.exists() and target.read_bytes() != data:
                raise ValueError(f"Refusing to overwrite modified vendor file: {name}")
        for name, data in entries.items():
            target = ROOT / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(data)
    print(f"Vendored {len(entries)} files; {sum(map(len, entries.values()))} bytes")


if __name__ == "__main__":
    main()

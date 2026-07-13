# -*- coding: utf-8 -*-
"""Nhung lai app-src.html vao index.html (the __bundler/template).

Quy trinh sua giao dien journal:
  1. Sua app-src.html
  2. python automation/rebuild_index.py
  3. Mo index.html kiem tra roi deploy Netlify
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "app-src.html"
IDX = ROOT / "index.html"

OPEN_TAG = '<script type="__bundler/template">'


def main():
    src = SRC.read_text(encoding="utf-8")
    idx = IDX.read_text(encoding="utf-8")

    start = idx.find(OPEN_TAG)
    if start == -1:
        print("[!] Khong tim thay the __bundler/template trong index.html")
        sys.exit(1)
    body_start = start + len(OPEN_TAG)
    # Template JSON escape '</' thanh '<\/' nen '</script>' dau tien la the dong that
    body_end = idx.find("</script>", body_start)
    if body_end == -1:
        print("[!] Khong tim thay the dong </script>")
        sys.exit(1)

    # Kiem tra template cu parse duoc (sanity check truoc khi ghi de)
    old_template = json.loads(idx[body_start:body_end])
    print(f"Template cu : {len(old_template):,} ky tu")
    print(f"app-src.html: {len(src):,} ky tu")

    new_json = json.dumps(src, ensure_ascii=False).replace("</", "<\\/")
    # Round-trip check
    assert json.loads(new_json) == src, "JSON round-trip that bai"

    new_idx = idx[:body_start] + new_json + idx[body_end:]
    IDX.write_text(new_idx, encoding="utf-8", newline="\n")
    print(f"OK — da ghi index.html ({len(new_idx):,} ky tu)")


if __name__ == "__main__":
    main()

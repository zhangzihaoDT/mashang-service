#!/usr/bin/env python
"""
smoke_test_official_document_render.py — 正式材料排版渲染 Skill Smoke Test

验证 render_official_document.py 是否能正常工作。
"""

import sys, subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

SAMPLE_MD = _REPO_ROOT / "skills" / "official_document_render" / "examples" / "project_application_sample.md"
SCRIPT = _REPO_ROOT / "scripts" / "render_official_document.py"
SMOKE_DIR = _REPO_ROOT / "outputs" / "smoke" / "official_document_render"


def main():
    print("=" * 60)
    print("  Smoke Test: official_document_render Skill")
    print("=" * 60)

    if not SAMPLE_MD.exists():
        print(f"✗ Sample not found: {SAMPLE_MD}")
        sys.exit(1)
    if not SCRIPT.exists():
        print(f"✗ Script not found: {SCRIPT}")
        sys.exit(1)

    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    basename = "项目申报书_示例"

    # Detect formats
    formats = []
    try:
        r = subprocess.run(["pandoc", "--version"], capture_output=True, timeout=10)
        if r.returncode == 0:
            formats.append("docx")
    except Exception:
        pass
    try:
        from weasyprint import HTML
        formats.append("pdf")
    except Exception:
        pass
    formats.append("html")

    formats_str = ",".join(formats)

    cmd = [
        sys.executable, str(SCRIPT),
        "--input", str(SAMPLE_MD),
        "--output-dir", str(SMOKE_DIR),
        "--basename", basename,
        "--formats", formats_str,
        "--title", "示例项目申报书",
    ]

    print(f"  Input:  {SAMPLE_MD}")
    print(f"  Output: {SMOKE_DIR}")
    print(f"  Formats: {formats_str}")
    print()

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    print(r.stdout)
    if r.stderr:
        print("  stderr:", r.stderr[:500])

    # Verify outputs
    print("=" * 60)
    print("  Verification")
    print("=" * 60)

    all_ok = True
    for ext in formats:
        f = SMOKE_DIR / f"{basename}.{ext}"
        if f.exists():
            size_kb = f.stat().st_size / 1024
            print(f"  ✓ {ext.upper()}: {f} ({size_kb:.0f} KB)")
        else:
            print(f"  ✗ {ext.upper()}: not found")
            all_ok = False

    print()
    if all_ok:
        print("  ✓ Smoke test PASSED")
    else:
        print("  ✗ Smoke test FAILED")
        sys.exit(1)

    print("=" * 60)


if __name__ == "__main__":
    main()

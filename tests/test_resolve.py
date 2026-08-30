"""
resolve_binary 通用二进制定位测试（纯本地，无第三方依赖）。

覆盖：
    1. 显式路径（explicit_path）优先
    2. PATH 命中（临时目录塞进 PATH）
    3. extra_candidates 兜底
    4. 常见安装位置默认候选（home 下的 .local/bin）
    5. 全部失败 → RuntimeError 且 hint 出现在消息里

运行：
    .venv\\Scripts\\python.exe tests\\test_resolve.py
"""

import os
import sys
import tempfile
from pathlib import Path

# 允许从任意 cwd 直接运行
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.mcp.resolve import resolve_binary  # noqa: E402


def _exe(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def _check(name: str, ok: bool) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    if not ok:
        raise AssertionError(f"断言失败: {name}")


def test_explicit_path_priority() -> None:
    """显式路径是文件时直接命中，即使 PATH 里没有。"""
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / _exe("my-tool")
        fake.write_bytes(b"MZ")
        found = resolve_binary(
            "my-tool",
            explicit_path=str(fake),
            hint="hint-xyz",
        )
        _check("explicit_path 命中", Path(found).resolve() == fake.resolve())


def test_explicit_path_falls_back_to_which() -> None:
    """显式路径不是文件时，把名字交给 PATH which 再试一次。"""
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / _exe("my-tool")
        fake.write_bytes(b"MZ")
        old_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = tmp
            found = resolve_binary("my-tool", explicit_path="my-tool")
            _check("explicit_path 非文件时回退 which", Path(found).resolve() == fake.resolve())
        finally:
            if old_path:
                os.environ["PATH"] = old_path
            else:
                os.environ.pop("PATH", None)


def test_path_hit() -> None:
    """PATH 中存在即可命中。"""
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / _exe("my-tool")
        fake.write_bytes(b"MZ")
        old_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = tmp
            found = resolve_binary("my-tool")
            _check("PATH 命中", Path(found).resolve() == fake.resolve())
        finally:
            if old_path:
                os.environ["PATH"] = old_path
            else:
                os.environ.pop("PATH", None)


def test_extra_candidates_fallback() -> None:
    """显式路径与 PATH 都失败时，extra_candidates 兜底。"""
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / _exe("my-tool")
        fake.write_bytes(b"MZ")
        found = resolve_binary(
            "my-tool",
            extra_candidates=(str(fake),),
        )
        _check("extra_candidates 兜底", Path(found).resolve() == fake.resolve())


def test_home_bin_fallback() -> None:
    """home 下的 .local/bin 默认候选。"""
    with tempfile.TemporaryDirectory() as tmp:
        bin_dir = Path(tmp) / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        fake = bin_dir / _exe("my-tool")
        fake.write_bytes(b"MZ")

        old_home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
        try:
            os.environ["USERPROFILE"] = tmp
            os.environ["HOME"] = tmp
            found = resolve_binary("my-tool")
            _check("home/.local/bin 兜底", Path(found).resolve() == fake.resolve())
        finally:
            if old_home:
                os.environ["USERPROFILE"] = old_home
                os.environ["HOME"] = old_home
            else:
                os.environ.pop("USERPROFILE", None)
                os.environ.pop("HOME", None)


def test_all_fail_raises() -> None:
    """全部查找手段失败 → RuntimeError，hint 出现在消息里。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_path = os.environ.get("PATH", "")
        old_home = os.environ.get("USERPROFILE")
        try:
            os.environ["PATH"] = tmp  # 空目录，which 必失败
            os.environ.pop("USERPROFILE", None)
            try:
                resolve_binary("definitely-not-installed-xyz", hint="请先安装 XYZ")
                _check("全失败抛 RuntimeError", False)
            except RuntimeError as exc:
                _check("全失败抛 RuntimeError", True)
                _check("hint 出现在消息里", "请先安装 XYZ" in str(exc))
                _check("名字出现在消息里", "definitely-not-installed-xyz" in str(exc))
        finally:
            if old_path:
                os.environ["PATH"] = old_path
            else:
                os.environ.pop("PATH", None)
            if old_home:
                os.environ["USERPROFILE"] = old_home


if __name__ == "__main__":
    test_explicit_path_priority()
    test_explicit_path_falls_back_to_which()
    test_path_hit()
    test_extra_candidates_fallback()
    test_home_bin_fallback()
    test_all_fail_raises()
    print()
    print("test_resolve: ALL PASS")

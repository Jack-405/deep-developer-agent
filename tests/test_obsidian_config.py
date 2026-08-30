"""
obsidian-mcp 接入配置测试（纯本地，不依赖 LLM / 网络 / pydantic-settings）。

覆盖：
    1. resolve_obsidian_bin：显式 bin_path 命中；缺失时抛 RuntimeError
    2. resolve_vault_path：显式存在返回绝对路径；不存在/为空返回 None
    3. is_obsidian_ready：bin / vault 任一缺失 → False，齐备 → True
    4. build_launch：command=bin、args=[vault]、env 字典

注意：不 import spec.py / registry.py（它们依赖 pydantic-settings，
在受限沙箱中会因 asyncio 无法导入而挂）；这里只测零依赖的纯函数。

运行：
    .venv\\Scripts\\python.exe tests\\test_obsidian_config.py
"""

import os
import sys
import tempfile
from pathlib import Path

# 允许从任意 cwd 直接运行: python tests/test_obsidian_config.py
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.mcp.servers.obsidian.config import (  # noqa: E402
    build_launch,
    is_obsidian_ready,
    resolve_obsidian_bin,
    resolve_vault_path,
)

_PASS = 0
_FAIL = 0


def check(label: str, condition: bool) -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"[PASS] {label}")
    else:
        _FAIL += 1
        print(f"[FAIL] {label}")


def test_resolve_obsidian_bin() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fake_bin = os.path.join(tmp, "obsidian-mcp.exe" if os.name == "nt" else "obsidian-mcp")
        Path(fake_bin).write_text("", encoding="utf-8")

        # 显式 bin_path 命中
        got = resolve_obsidian_bin(bin_path=fake_bin)
        check("显式 bin_path 命中", got == os.path.abspath(fake_bin))

        # 显式为空且 PATH 无该命令 → RuntimeError
        try:
            resolve_obsidian_bin(bin_path="")
            check("缺失时抛 RuntimeError", False)
        except RuntimeError:
            check("缺失时抛 RuntimeError", True)


def test_resolve_vault_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # 存在的目录 → 绝对路径
        got = resolve_vault_path(vault_path=tmp)
        check("存在的目录返回绝对路径", got == os.path.abspath(tmp))

        # 不存在的目录 → None
        missing = os.path.join(tmp, "nope")
        check("不存在的目录返回 None", resolve_vault_path(vault_path=missing) is None)

    # 空串 → None
    check("空配置返回 None", resolve_vault_path(vault_path="") is None)
    check("空白配置返回 None", resolve_vault_path(vault_path="   ") is None)


def test_is_obsidian_ready() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fake_bin = os.path.join(tmp, "obsidian-mcp.exe" if os.name == "nt" else "obsidian-mcp")
        Path(fake_bin).write_text("", encoding="utf-8")
        vault = os.path.join(tmp, "vault")
        os.makedirs(vault, exist_ok=True)

        check("bin+vault 齐备 → True", is_obsidian_ready(bin_path=fake_bin, vault_path=vault) is True)
        check("vault 缺失 → False", is_obsidian_ready(bin_path=fake_bin, vault_path="") is False)
        check("bin 缺失 → False", is_obsidian_ready(bin_path="", vault_path=vault) is False)


def test_build_launch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fake_bin = os.path.join(tmp, "obsidian-mcp.exe" if os.name == "nt" else "obsidian-mcp")
        Path(fake_bin).write_text("", encoding="utf-8")
        vault = os.path.join(tmp, "vault")
        os.makedirs(vault, exist_ok=True)

        launch = build_launch(bin_path=fake_bin, vault_path=vault)
        check("command 是 bin", launch.command == os.path.abspath(fake_bin))
        check("args=[vault]", launch.args == [os.path.abspath(vault)])
        check("env 是 dict", isinstance(launch.env, dict))
        check("url 为空(stdio)", launch.url is None)


if __name__ == "__main__":
    test_resolve_obsidian_bin()
    test_resolve_vault_path()
    test_is_obsidian_ready()
    test_build_launch()
    print()
    if _FAIL:
        print(f"test_obsidian_config: {_FAIL} FAILED, {_PASS} passed")
        raise SystemExit(1)
    print(f"test_obsidian_config: ALL PASS ({_PASS})")

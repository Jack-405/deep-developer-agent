"""
通用（配置驱动）MCP server 测试（纯本地，不依赖 LLM / pydantic-settings）。

覆盖：
    1. parse_mcp_extra：空串 / 非法 JSON / 非数组 → []
    2. 合法项解析：name/command/args/scope/env/enabled/prompt/prompt_file
    3. 缺失 name/command、非法 scope、args/env 类型错 → 跳过该项
    4. GenericSpec.enabled() / applicable() / ready()
    5. build_launch：command/args/env 合并（配置项覆盖宿主环境变量）
    6. build_prompt：内联 prompt 优先；prompt_file 读取；都无 → None
    7. 协议方法可用（is_enabled 字段不遮蔽 enabled() 方法）

注意：不 import spec.py / registry.py / settings.py（依赖 pydantic-settings，
受限沙箱中会因 asyncio 无法导入而挂）；这里只测零依赖的 generic.py。

运行：
    .venv\\Scripts\\python.exe tests\\test_mcp_generic.py
"""

import os
import sys
import tempfile
from pathlib import Path

# 允许从任意 cwd 直接运行
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.mcp.servers.generic import GenericSpec, parse_mcp_extra  # noqa: E402

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


def test_parse_empty_invalid() -> None:
    check("空串 → []", parse_mcp_extra("") == [])
    check("空白 → []", parse_mcp_extra("   ") == [])
    check("非法 JSON → []", parse_mcp_extra("not json") == [])
    check("非数组 → []", parse_mcp_extra('{"name": "x"}') == [])


def test_parse_valid_item() -> None:
    raw = (
        '[{"name": "my-mcp", "command": "npx", "args": ["-y", "@srv"],'
        ' "scope": "workspace", "env": {"K": "v"}, "enabled": false,'
        ' "prompt": "使用引导"}]'
    )
    specs = parse_mcp_extra(raw)
    check("合法项解析出 1 个", len(specs) == 1)
    spec = specs[0]
    check("name", spec.name == "my-mcp")
    check("command", spec.command == "npx")
    check("args", spec.args == ["-y", "@srv"])
    check("scope", spec.scope == "workspace")
    check("env", spec.env == {"K": "v"})
    check("enabled=false 映射到 is_enabled", spec.is_enabled is False)
    check("prompt", spec.prompt == "使用引导")


def test_parse_invalid_items_skipped() -> None:
    raw = (
        '[{"command": "npx"},'
        ' {"name": "n1"},'
        ' {"name": "n2", "command": "x", "scope": "bad"},'
        ' {"name": "n3", "command": "x", "args": "not-list"},'
        ' {"name": "n4", "command": "x", "env": "not-dict"},'
        ' {"name": "ok", "command": "x"}]'
    )
    specs = parse_mcp_extra(raw)
    check("非法项全部跳过，仅合法项保留", len(specs) == 1)
    check("保留下的是合法项", specs[0].name == "ok")


def test_protocol_methods() -> None:
    spec = GenericSpec(name="m", command="npx")
    # is_enabled 字段不遮蔽 enabled() 协议方法
    check("enabled() 是方法可调用", callable(spec.enabled))
    check("enabled() 默认 True", spec.enabled() is True)
    check("applicable 恒 True", spec.applicable("/some/ws") is True)
    check("transport stdio", spec.transport == "stdio")


def test_ready() -> None:
    # ready() 对可定位命令返回 True（shutil.which 或绝对路径）
    py = os.path.join(os.path.dirname(sys.executable), "python.exe") if os.name == "nt" \
        else sys.executable
    spec = GenericSpec(name="m", command=py)
    check("绝对路径存在的命令 ready", spec.ready() is True)

    # 不存在的命令 → False（不抛异常）
    spec2 = GenericSpec(name="m", command="/definitely/not/exist-bin-xyz")
    check("不存在的命令 ready=False", spec2.ready() is False)


def test_build_launch() -> None:
    spec = GenericSpec(
        name="m", command="npx", args=["-y", "@srv"], env={"FOO": "bar"}
    )
    launch = spec.build_launch()
    check("command", launch.command == "npx")
    check("args", launch.args == ["-y", "@srv"])
    check("env 是宿主环境变量的超集", all(k in launch.env for k in os.environ))
    check("env 含配置附加项", launch.env.get("FOO") == "bar")


def test_build_prompt() -> None:
    # 内联 prompt 优先
    spec = GenericSpec(name="m", command="x", prompt="inline")
    check("内联 prompt", spec.build_prompt() == "inline")

    # prompt_file 读取（相对项目根）
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "guide.md"
        p.write_text("file guide", encoding="utf-8")
        spec = GenericSpec(name="m", command="x", prompt_file=str(p))
        check("prompt_file 读取", spec.build_prompt() == "file guide")

    # 都不存在 → None
    check("无 prompt → None", GenericSpec(name="m", command="x").build_prompt() is None)

    # prompt_file 不存在 → None（不抛异常）
    spec = GenericSpec(name="m", command="x", prompt_file="/no/such/file.md")
    check("prompt_file 缺失 → None", spec.build_prompt() is None)


if __name__ == "__main__":
    test_parse_empty_invalid()
    test_parse_valid_item()
    test_parse_invalid_items_skipped()
    test_protocol_methods()
    test_ready()
    test_build_launch()
    test_build_prompt()

    print()
    if _FAIL:
        print(f"test_mcp_generic: {_FAIL} FAILED, {_PASS} passed")
        sys.exit(1)
    print(f"test_mcp_generic: ALL PASS ({_PASS})")

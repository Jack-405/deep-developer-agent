"""
Skills 注入冒烟测试（纯本地，不依赖 LLM / 网络）。

覆盖：
    1. resolve_skills_dir：仓库内置 skills 目录存在，5 个 Godot skill 的 SKILL.md 就位
    2. 路径自洽：SkillsMiddleware 展示路径 → CompositeBackend 路由剥离前缀
       → route backend 物理映射，最终可读
    3. build_skills_middleware：Godot 项目注入 / 非 Godot 项目跳过（(None, {})）
    4. middleware.sources：展示路径与路由前缀一致（/godot-skills-main/）
    5. CompositeBackend 路由：read_file 展示路径能读到 SKILL.md 内容
    6. ls("/") 聚合时能看到 skill 路由目录

运行：
    .venv\\Scripts\\python.exe tests\\test_skills.py
"""

import os
import sys
import tempfile
from pathlib import Path

# 允许从任意 cwd 直接运行: python tests/test_skills.py
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.skills.manager import (
    GODOT_SKILLS_DIR,
    GODOT_SKILLS_LABEL,
    GODOT_SKILLS_ROUTE_PREFIX,
    SKILLS_ROOT,
    resolve_skills_dir,
)
import backend.skills.manager as skills_manager  # noqa: E402  (import after sys.path fix)

# deepagents 依赖 asyncio/Winsock，在受限沙箱中可能无法导入；
# 此时跳过 backend 相关测试（用户本机可正常运行全部用例）。
try:
    from deepagents.backends import CompositeBackend, FilesystemBackend

    DEEPAGENTS_AVAILABLE = True
except Exception:  # noqa: BLE001 - 环境受限时跳过
    DEEPAGENTS_AVAILABLE = False

PASS = 0


def check(name: str, condition: bool) -> None:
    global PASS
    if not condition:
        raise AssertionError(f"FAIL: {name}")
    PASS += 1
    print(f"  ok - {name}")


# 期望的 5 个 Godot skill 目录名
EXPECTED_SKILL_DIRS = [
    "godot",
    "godot-gdscript",
    "godot-csharp",
    "godot-gdextension",
    "godot-shader",
]


def test_resolve_skills_dir() -> None:
    print("[resolve_skills_dir]")
    root = resolve_skills_dir()
    check("skills 根目录存在", root.is_dir())
    check("根目录指向 backend/skills", root == SKILLS_ROOT)

    godot_skills = root / GODOT_SKILLS_DIR
    check("godot-skills-main 目录存在", godot_skills.is_dir())

    for name in EXPECTED_SKILL_DIRS:
        skill_md = godot_skills / name / "SKILL.md"
        check(f"SKILL.md 就位: {name}", skill_md.is_file())
    print()


def test_route_path_mapping() -> None:
    """验证展示路径与物理文件的映射自洽（不依赖 deepagents）。

    映射规则（与 manager.py 注释一致）：
        read_file("/godot-skills-main/<skill>/SKILL.md")
        → CompositeBackend 剥离前缀 "/godot-skills-main/"
        → "/<skill>/SKILL.md"
        → route backend（root=SKILLS_ROOT/godot-skills-main, virtual_mode）
        → <SKILLS_ROOT>/godot-skills-main/<skill>/SKILL.md
    """
    print("[route path mapping]")
    godot_skills = SKILLS_ROOT / GODOT_SKILLS_DIR
    for name in EXPECTED_SKILL_DIRS:
        # 模型看到的展示路径
        shown_path = f"{GODOT_SKILLS_ROUTE_PREFIX}{name}/SKILL.md"
        # CompositeBackend._route_for_path：剥离前缀后补回 "/"
        # （suffix = path[len(prefix):] → backend_path = f"/{suffix}"）
        stripped = "/" + shown_path[len(GODOT_SKILLS_ROUTE_PREFIX) :]
        check("剥离前缀后以 / 开头", stripped.startswith("/"))
        # route backend virtual_mode 映射到物理文件
        physical = (godot_skills / stripped.lstrip("/")).resolve()
        check(f"物理文件可达: {name}", physical.is_file())
    print()


def _make_godot_workspace(tmp: str) -> None:
    """在临时目录下创建一个 Godot 项目（含一层子目录场景也覆盖）。"""
    Path(tmp, "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="test"\n',
        encoding="utf-8",
    )


def test_build_skills_middleware() -> None:
    print("[build_skills_middleware]")
    if not DEEPAGENTS_AVAILABLE:
        print("  (skip) deepagents 不可导入，跳过")
        return

    original = skills_manager._is_godot_workspace
    try:
        # Godot 项目 → 注入
        skills_manager._is_godot_workspace = lambda w: True
        with tempfile.TemporaryDirectory() as tmp:
            middleware, routes = skills_manager.build_skills_middleware(tmp)
            check("Godot 项目返回 middleware", middleware is not None)
            check("sources 与展示前缀一致", middleware.sources == [GODOT_SKILLS_ROUTE_PREFIX])
            check("source label 为 Godot", middleware.source_labels == [GODOT_SKILLS_LABEL])
            check("routes 含 skill 前缀", GODOT_SKILLS_ROUTE_PREFIX in routes)
            check("route backend 为 FilesystemBackend",
                  isinstance(routes[GODOT_SKILLS_ROUTE_PREFIX], FilesystemBackend))

        # 非 Godot 项目 → 跳过
        skills_manager._is_godot_workspace = lambda w: False
        with tempfile.TemporaryDirectory() as tmp:
            middleware, routes = skills_manager.build_skills_middleware(tmp)
            check("非 Godot 项目返回 (None, {})", middleware is None and routes == {})
    finally:
        skills_manager._is_godot_workspace = original
    print()


def test_real_godot_detection() -> None:
    """真实探测：临时目录建 project.godot 应判定为 Godot 项目。

    仅当未显式配置 DEEPDEV_GODOT_PROJECT_PATH 时执行（显式配置会
    覆盖自动探测，避免用户本机配置干扰断言）。
    """
    print("[real godot detection]")
    try:
        from backend.config.settings import settings
        from backend.mcp.servers.godot.config import is_godot_workspace
    except Exception:  # noqa: BLE001 - 受限环境（无 asyncio）跳过
        print("  (skip) 环境受限无法导入 settings/config，跳过")
        return
    if settings.DEEPDEV_GODOT_PROJECT_PATH.strip():
        print("  (skip) DEEPDEV_GODOT_PROJECT_PATH 已显式配置，跳过")
        return

    with tempfile.TemporaryDirectory() as tmp:
        check("空目录不是 Godot 项目", not is_godot_workspace(tmp))
        _make_godot_workspace(tmp)
        check("含 project.godot 判定为 Godot 项目", is_godot_workspace(tmp))

        # 一层子目录场景
        with tempfile.TemporaryDirectory() as tmp2:
            sub = Path(tmp2) / "sub"
            sub.mkdir()
            check("子目录无 project.godot 不是 Godot 项目", not is_godot_workspace(tmp2))
            (sub / "project.godot").write_text("x", encoding="utf-8")
            check("一层子目录含 project.godot 判定为 Godot 项目", is_godot_workspace(tmp2))
    print()


def test_composite_route_read() -> None:
    """模拟模型 read_file 展示路径：CompositeBackend 路由应读到 SKILL.md 内容。"""
    print("[composite route read]")
    if not DEEPAGENTS_AVAILABLE:
        print("  (skip) deepagents 不可导入，跳过")
        return

    godot_skills = SKILLS_ROOT / GODOT_SKILLS_DIR
    route_backend = FilesystemBackend(
        root_dir=godot_skills,
        virtual_mode=True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        composite = CompositeBackend(
            default=FilesystemBackend(root_dir=tmp, virtual_mode=True),
            routes={GODOT_SKILLS_ROUTE_PREFIX: route_backend},
        )

        for name in EXPECTED_SKILL_DIRS:
            shown_path = f"{GODOT_SKILLS_ROUTE_PREFIX}{name}/SKILL.md"
            result = composite.read(shown_path)
            check(f"read 无错误: {name}", result.error is None or result.error == "")
            file_data = result.file_data or {}
            check(f"读到内容: {name}", bool(file_data.get("content")))
            content = file_data.get("content") or ""
            check(f"含 YAML frontmatter: {name}", content.startswith("---"))

        # ls("/") 聚合应展示 skill 路由目录
        root_ls = composite.ls("/")
        paths = {e["path"] for e in (root_ls.entries or [])}
        check("ls('/') 展示 skill 路由目录", GODOT_SKILLS_ROUTE_PREFIX in paths)

        # ls(前缀) 应列出 5 个 skill 目录
        dir_ls = composite.ls(GODOT_SKILLS_ROUTE_PREFIX)
        dirs = {e["path"] for e in (dir_ls.entries or [])}
        check("ls 前缀列出全部 skill 目录",
              all(f"{GODOT_SKILLS_ROUTE_PREFIX}{name}/" in dirs for name in EXPECTED_SKILL_DIRS))
    print()


if __name__ == "__main__":
    test_resolve_skills_dir()
    test_route_path_mapping()
    test_build_skills_middleware()
    test_real_godot_detection()
    test_composite_route_read()
    print(f"\n全部通过：{PASS} 项")

import json
import os
from pathlib import Path
from json import JSONDecodeError


# 锚定到项目根目录，保证 CLI 在任何工作目录下启动都能读写注册表
_REGISTRY_DIR = Path(__file__).resolve().parents[2] / "projects"
REGISTRY_PATH = _REGISTRY_DIR / "registry.json"


def normalize_path(path: str | Path) -> str:
    """路径规范化（身份比较键）。

    展开用户目录、解析为绝对路径、统一分隔符；
    Windows 下同时统一大小写（盘符与路径段，大小写不敏感）。

    注意：
        该结果用于「身份判断」与「内存 sources 构造」，
        不用于磁盘访问路径的展示（展示请用 ``Path(path).expanduser().resolve()``）。
    """
    resolved = Path(path).expanduser().resolve()
    return os.path.normcase(str(resolved))


def _empty_registry() -> dict:
    return {
        "projects": [],
        "current": None,
    }


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return _empty_registry()

    try:
        with REGISTRY_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)
    except JSONDecodeError:
        return _empty_registry()


def save_registry(registry: dict) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

    with REGISTRY_PATH.open("w", encoding="utf-8") as file:
        json.dump(registry, file, ensure_ascii=False, indent=2)


def list_projects() -> list[dict]:
    return load_registry().get("projects", [])


def get_current_path() -> str | None:
    return load_registry().get("current")


def save_project(path: str) -> dict:
    project_path = Path(path).expanduser().resolve()
    project = {
        "name": project_path.name,
        "path": str(project_path),
    }

    registry = load_registry()
    projects = registry.get("projects", [])

    # 去重比较使用规范化路径，避免同一目录因大小写 / 尾斜杠写法不同被重复登记
    project_key = normalize_path(project["path"])
    if not any(normalize_path(existing.get("path", "")) == project_key for existing in projects):
        projects.append(project)

    registry["projects"] = projects
    registry["current"] = project["path"]
    save_registry(registry)

    return project

from pathlib import Path

from backend.workspace import registry


class WorkspaceManager:
    def get_current(self) -> str | None:
        current = registry.get_current_path()

        if not current:
            return None

        current_path = Path(current).expanduser().resolve()

        if not current_path.exists() or not current_path.is_dir():
            return None

        return str(current_path)

    def set_current(self, path: str) -> dict:
        project_path = Path(path).expanduser().resolve()

        if not project_path.exists():
            raise FileNotFoundError(f"Workspace path does not exist: {project_path}")

        if not project_path.is_dir():
            raise NotADirectoryError(f"Workspace path is not a directory: {project_path}")

        return registry.save_project(str(project_path))

    def require_current(self) -> str:
        current = self.get_current()

        if current is None:
            raise RuntimeError("No workspace selected.")

        return current


workspace_manager = WorkspaceManager()

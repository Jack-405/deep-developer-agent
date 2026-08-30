"""
MCPManager.collect 串行启动行为验证（需本机运行：沙箱 asyncio 起不来）。

覆盖（用 FakeSpec/FakeSession 替身，不碰真实子进程）：
    1. 多个适用 server 串行启动（start 无重叠，peak == 1）
    2. loaded_specs / tools 保持 registry 顺序（冲突改名优先级不变）
    3. 单个 server 启动失败不影响其他 server（异常隔离）
    4. 会话缓存复用（再次 collect 不重启已加载 server）
    5. 跨 server 同名工具时后加载方改名，顺序即优先级

注：必须串行。曾用 asyncio.gather 并发启动，但 mcp 的 stdio_client /
ClientSession 内部用 anyio 任务组（cancel scope），上下文必须"进入与退出
在同一 task"；并发版在 REPL 退出 shutdown 时（主 task 关闭 gather task
里进入的上下文）抛 RuntimeError: Attempted to exit cancel scope in a
different task（2026-08 回归，已回退串行）。

运行：
    python tests/test_mcp_client.py
"""

import sys
from pathlib import Path

# 允许从任意 cwd 直接运行
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_IMPORT_OK = True
try:
    import asyncio  # 沙箱 Windows 下 import 即挂（WinError 10106）
    import backend.mcp.client as client_module  # noqa: E402
except Exception as exc:  # 沙箱：asyncio 初始化失败 / import 链触发
    _IMPORT_OK = False
    _IMPORT_ERR = exc

_PASS = 0
_FAIL = 0


def check(label: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"[PASS] {label}")
    else:
        _FAIL += 1
        print(f"[FAIL] {label}")


class FakeSpec:
    """最小 MCPServerSpec 替身：只实现 collect 用到的成员。"""

    def __init__(self, name, fail_start=False, applicable=True):
        self.name = name
        self.scope = "workspace"
        self.transport = "stdio"
        self.fail_start = fail_start
        self._applicable = applicable

    def enabled(self):
        return True

    def ready(self):
        return True

    def applicable(self, workspace):
        return self._applicable

    def build_launch(self):
        return None


class FakeTool:
    def __init__(self, name):
        self.name = name


class FakeSession:
    """MCPSession 替身：共享 tracker 统计并发度与调用次数。

    start 内先自增 active 再 sleep——若并发，两个 server 会同时处于
    active 状态，peak 记录到的最大值即并发峰值（串行为 1）。
    """

    tracker = None  # 共享 dict: {"active","peak","starts","specs"}

    def __init__(self, server_name, launch):
        self.server_name = server_name
        self.tools = None

    async def start(self):
        t = self.tracker
        t["active"] += 1
        t["peak"] = max(t["peak"], t["active"])
        t["starts"] += 1
        await asyncio.sleep(0.05)
        t["active"] -= 1
        spec = t["specs"][self.server_name]
        if spec.fail_start:
            raise RuntimeError(f"{self.server_name} start failed")
        self.tools = [FakeTool(f"{self.server_name}_tool")]

    async def get_tools(self):
        return list(self.tools or [])

    async def close(self):
        pass


def _patch_session(tracker):
    """临时替换 client_module.MCPSession，返回恢复函数。"""
    old = client_module.MCPSession
    FakeSession.tracker = tracker
    client_module.MCPSession = FakeSession

    def restore():
        client_module.MCPSession = old
        FakeSession.tracker = None  # 完全还原，避免跨测试残留

    return restore


def _run(coro):
    return asyncio.run(coro)


async def _collect(specs, tracker):
    restore = _patch_session(tracker)
    try:
        mgr = client_module.MCPManager(registry=specs)
        loaded, tools = await mgr.collect("ws")
        return mgr, loaded, tools
    finally:
        restore()


def test_serial_start():
    # 串行启动（2026-08 回归修复）：asyncio.gather 并发会让 mcp 的
    # stdio_client / ClientSession 的 anyio 上下文在"进入的 task"之外被
    # 关闭，REPL 退出 shutdown 时抛 RuntimeError: Attempted to exit
    # cancel scope in a different task。因此必须串行：start 无重叠。
    specs = [FakeSpec("a"), FakeSpec("b")]
    tracker = {"active": 0, "peak": 0, "starts": 0, "specs": {s.name: s for s in specs}}
    mgr, loaded, tools = _run(_collect(specs, tracker))

    check("server 串行启动（peak == 1，无并发重叠）", tracker["peak"] == 1)
    check("每个 server 只 start 一次", tracker["starts"] == 2)
    check("loaded_specs 顺序 == registry 顺序",
          [s.name for s in loaded] == ["a", "b"])
    check("工具按 registry 顺序聚合",
          [t.name for t in tools] == ["a_tool", "b_tool"])


def test_order_preserved_with_skip():
    # b 不适用被跳过，loaded 顺序仍为 [a, c]（registry 顺序，非完成顺序）
    specs = [FakeSpec("a"), FakeSpec("b", applicable=False), FakeSpec("c")]
    tracker = {"active": 0, "peak": 0, "starts": 0, "specs": {s.name: s for s in specs}}
    _, loaded, tools = _run(_collect(specs, tracker))

    check("跳过不适用 server", [s.name for s in loaded] == ["a", "c"])
    check("工具顺序不含跳过项", [t.name for t in tools] == ["a_tool", "c_tool"])


def test_failure_isolation():
    specs = [FakeSpec("a", fail_start=True), FakeSpec("b")]
    tracker = {"active": 0, "peak": 0, "starts": 0, "specs": {s.name: s for s in specs}}
    try:
        mgr, loaded, tools = _run(_collect(specs, tracker))
        check("启动失败不阻断整体", True)
    except Exception:
        check("启动失败不阻断整体", False)
        return

    check("失败 server 不在 loaded 中", [s.name for s in loaded] == ["b"])
    check("失败 server 的工具未聚合", [t.name for t in tools] == ["b_tool"])
    check("失败 server 会话已释放",
          ("a", "ws") not in mgr._sessions and ("b", "ws") in mgr._sessions)


def test_cache_reuse():
    specs = [FakeSpec("a"), FakeSpec("b")]
    tracker = {"active": 0, "peak": 0, "starts": 0, "specs": {s.name: s for s in specs}}
    restore = _patch_session(tracker)
    try:
        mgr = client_module.MCPManager(registry=specs)
        _run(mgr.collect("ws"))
        loaded2, tools2 = _run(mgr.collect("ws"))
    finally:
        restore()

    check("二次 collect 不重启会话（starts == 2）", tracker["starts"] == 2)
    check("二次 collect 结果一致",
          [t.name for t in tools2] == ["a_tool", "b_tool"])


def test_conflict_rename_order():
    # 两 server 都有同名工具 "dup"：顺序即优先级，后加载方 b 改名
    specs = [FakeSpec("a"), FakeSpec("b")]
    tracker = {"active": 0, "peak": 0, "starts": 0, "specs": {s.name: s for s in specs}}

    class DupSession(FakeSession):
        async def start(self):
            t = self.tracker
            t["active"] += 1
            t["peak"] = max(t["peak"], t["active"])
            t["starts"] += 1
            await asyncio.sleep(0.05)
            t["active"] -= 1
            self.tools = [FakeTool("dup")]

    restore = _patch_session(tracker)
    old_cls = client_module.MCPSession
    client_module.MCPSession = DupSession
    try:
        mgr = client_module.MCPManager(registry=specs)
        _, tools = _run(mgr.collect("ws"))
    finally:
        client_module.MCPSession = old_cls
        restore()

    check("先加载方保名、后加载方改名",
          [t.name for t in tools] == ["dup", "b_dup"])


if __name__ == "__main__":
    if not _IMPORT_OK:
        print(f"跳过 test_mcp_client：import backend.mcp.client 失败（{_IMPORT_ERR}）")
        print("本测试需在用户本机运行（沙箱 asyncio 起不来）")
        sys.exit(0)

    test_serial_start()
    test_order_preserved_with_skip()
    test_failure_isolation()
    test_cache_reuse()
    test_conflict_rename_order()

    print()
    if _FAIL:
        print(f"test_mcp_client: {_FAIL} FAILED, {_PASS} passed")
        sys.exit(1)
    print(f"test_mcp_client: ALL PASS ({_PASS})")

"""支持 `python -m cli` 启动。"""

import asyncio

from cli.main import main

if __name__ == "__main__":
    asyncio.run(main())

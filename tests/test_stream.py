import asyncio

from backend.agent.factory import create_agent


async def test_stream():

    agent = await create_agent()

    async for event in agent.astream_events(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "你好"
                }
            ]
        },
        version="v2"
    ):
        print(
            event["event"],
            event.get("name")
        )


if __name__ == "__main__":
    asyncio.run(test_stream())
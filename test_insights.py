import asyncio
from httpx import Client

def test():
    with Client(base_url="http://localhost:8001") as client:
        res = client.get("/signals/insights")
        print("Status:", res.status_code)
        print("Insights:", res.json())

test()

import asyncio
import sys
from platform.backend.api.predict import predict_all_bars

res = predict_all_bars()
print("Run result:", len(res))
for p in res:
    print(p)

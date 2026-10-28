"""`python -m findings`: write findings/findings.json and findings/MEMO.md."""

import time

from findings import build, memo

start = time.monotonic()
result = build.build()
build.write(result)
memo.write(result)
print(
    f"findings/findings.json ({result['status']}, data through {result['data']['data_end']}, "
    f"{len(result['queries'])} queries) and findings/MEMO.md in {time.monotonic() - start:.0f} s"
)

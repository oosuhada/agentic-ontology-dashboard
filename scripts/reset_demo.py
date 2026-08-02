#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset local Factory Signal Board demo state")
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    args = parser.parse_args()
    request = Request(f"{args.api.rstrip('/')}/api/demo/reset", method="POST")
    with urlopen(request, timeout=10) as response:
        payload = json.load(response)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check that the PaddleOCR-VL HTTP endpoint is reachable and returns JSON."""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8888/")
    parser.add_argument(
        "--trust-env",
        action="store_true",
        help="Use HTTP_PROXY/HTTPS_PROXY from the environment (disabled by default)",
    )
    args = parser.parse_args()

    opener = (
        urllib.request.build_opener()
        if args.trust_env
        else urllib.request.build_opener(urllib.request.ProxyHandler({}))
    )

    try:
        with opener.open(args.url, timeout=10) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            print(json.dumps({"reachable": True, "status": response.status, "body": body}))
    except urllib.error.HTTPError as exc:
        # A 404 still proves that the app is listening; 5xx means the service or
        # its upstream model process is unhealthy.
        reachable = exc.code < 500
        print(json.dumps({"reachable": reachable, "status": exc.code, "body": str(exc)}))
        if not reachable:
            raise SystemExit(1) from exc
    except OSError as exc:
        raise SystemExit(f"PaddleOCR service is not reachable: {exc}") from exc


if __name__ == "__main__":
    main()

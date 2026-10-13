from __future__ import annotations

import argparse
import os

import uvicorn


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地 STEP 比对查看器")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port 必须在 1 到 65535 之间")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.no_browser:
        os.environ.pop("STEP_VIEWER_OPEN_BROWSER", None)
    else:
        os.environ["STEP_VIEWER_OPEN_BROWSER"] = "1"
        os.environ["STEP_VIEWER_PORT"] = str(args.port)
    uvicorn.run("step_viewer.app:app", host="127.0.0.1", port=args.port, reload=False)


if __name__ == "__main__":
    main()

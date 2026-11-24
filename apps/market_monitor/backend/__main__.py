"""Refresh upstream projections or run a local preview."""

import argparse
import json
import sys
from wsgiref.simple_server import make_server

from .snapshot import (
    SOURCES, build_insurance, build_miit, import_snapshot, miit_file, publish,
    snapshot_dir, snapshot_lock,
)
from .web import create_app


def refresh(selected):
    directory = snapshot_dir()
    failed = False
    with snapshot_lock(directory):
        builders = {"insurance": build_insurance, "miit": lambda: build_miit(miit_file())}
        for source in (SOURCES if selected == "all" else (selected,)):
            try:
                snapshot = builders[source]()
                publish(directory, source, snapshot)
                print(f"{source}: {len(snapshot['months'])} 个月，最新 {snapshot['latest_month']}")
            except Exception as exc:
                print(f"{source}: 刷新失败，保留原快照。{exc}", file=sys.stderr)
                failed = True
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description="中国乘用车市场观察台")
    commands = parser.add_subparsers(dest="command", required=True)
    update = commands.add_parser("refresh", help="从现有上游数据生成月度快照")
    update.add_argument("--source", choices=("all", *SOURCES), default="all")
    ingest = commands.add_parser("import-snapshot", help="从标准输入安装应用快照")
    ingest.add_argument("--source", choices=SOURCES, required=True)
    serve = commands.add_parser("serve", help="在本机 127.0.0.1 预览")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--local", action="store_true", help="仅本机预览，关闭认证")
    args = parser.parse_args()
    if args.command in {"refresh", "import-snapshot"}:
        try:
            if args.command == "refresh":
                return refresh(args.source)
            snapshot = json.load(sys.stdin)
            import_snapshot(snapshot_dir(), args.source, snapshot)
            print(f"{args.source}: 已安装 {snapshot['latest_month']} 快照")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print(f"快照操作失败：{exc}", file=sys.stderr)
            return 1
        return 0
    with make_server("127.0.0.1", args.port, create_app(local=args.local)) as server:
        print(f"Market Monitor · http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

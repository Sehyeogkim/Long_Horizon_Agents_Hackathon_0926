import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Tomato Liquid/GPT-5 chronological observation MVP")
    commands = parser.add_subparsers(dest="command", required=True)
    replay = commands.add_parser("run")
    replay.add_argument("--manifest", type=Path, default=Path("data/samples/tomato_18day/observations.jsonl"))
    replay.add_argument("--output-dir", type=Path, default=Path("data/runs"))
    replay.add_argument("--variant", choices=["A", "B", "C"], default="C")
    replay.add_argument("--backend", choices=["local", "rawtree"], default="local")
    replay.add_argument("--run-id")
    replay.add_argument("--limit", type=int)
    replay.add_argument("--max-gap-hours", type=float, default=72)
    replay.add_argument("--max-gpt-calls", type=int, default=20)
    replay.add_argument("--max-api-cost-usd", type=float, default=1)
    report = commands.add_parser("report")
    report.add_argument("run_dirs", nargs="+", type=Path)
    report.add_argument("--output", type=Path, default=Path("reports/tomato_demo.html"))
    args = parser.parse_args()
    if args.command == "run":
        from .runner import run
        kwargs = vars(args).copy()
        kwargs.pop("command")
        result = run(**kwargs)
    else:
        from .report import build_report
        result = build_report(args.run_dirs, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

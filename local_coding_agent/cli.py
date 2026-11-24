"""Compact CLI for the offline coding intelligence agent."""
import argparse
import json
from pathlib import Path
from . import LocalCodingAgent


def save_result(root, destination, result):
    root = Path(root).resolve()
    path = Path(destination).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if path == root or root not in path.parents:
        raise ValueError("Output must remain inside project root.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    return path.relative_to(root).as_posix()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline Laiba repository coding agent"
    )
    parser.add_argument("command", choices=("analyze", "feature", "context"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--request", default="")
    parser.add_argument("--output", default="reports/local_coding_agent_report.json")
    args = parser.parse_args(argv)

    if args.command in {"feature", "context"} and not args.request.strip():
        parser.error("--request is required for feature and context commands")

    try:
        agent = LocalCodingAgent(args.root)
        agent.scan()
        report = agent.analyze()

        if args.command == "feature":
            result = agent.analyze_feature(args.request)
        elif args.command == "context":
            result = agent.build_context(args.request)
        else:
            result = report

        saved = save_result(agent.root, args.output, result)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print("Report saved:", saved)
    if args.command == "analyze":
        print("Files:", len(report["files"]),
              "| Python parsed:", report["python_files_parsed"],
              "| Findings:", len(report["findings"]),
              "| Warnings:", len(report.get("warnings", [])))
    elif args.command == "feature":
        locations = result["feature_locations"]
        print("Feature matches:", len(locations))
        for item in locations[:8]:
            symbols = item.get("matching_symbols", [])
            if symbols:
                for symbol in symbols[:4]:
                    print("{}:{} {}".format(
                        item["path"], symbol["line"],
                        symbol["qualified_name"]
                    ))
            else:
                print(item["path"])
    else:
        print("Context matches:", len(result["matches"]),
              "| Characters:", result["characters"],
              "| Truncated:", result["truncated"])


if __name__ == "__main__":
    main()

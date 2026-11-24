"""Command line interface for the offline coding agent."""
import argparse
import json
from .agent import LocalCodingAgent

def main():
    parser = argparse.ArgumentParser(description="Offline Laiba repository coding agent")
    parser.add_argument("command", choices=("analyze", "feature", "context"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--request", default="")
    parser.add_argument("--output", default="reports/local_coding_agent_report.json")
    args = parser.parse_args()
    if args.command in {"feature", "context"} and not args.request.strip():
        parser.error("--request is required for feature and context commands")

    agent = LocalCodingAgent(args.root)
    agent.scan()
    report = agent.analyze()

    if args.command == "feature":
        result = agent.analyze_feature(args.request)
    elif args.command == "context":
        result = agent.build_context(args.request)
    else:
        result = report
        print("Report:", agent.save_report(args.output))

    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

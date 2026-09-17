"""Local CLI. No upload, cloud service, or biomechanical interpretation."""
import argparse
import json
import sys
from pathlib import Path
from .core import extract


def write_json(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Experimental projected 2D cycling measurements")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "video"):
        command = commands.add_parser(name)
        command.add_argument("input", help="Annotated JSON" if name == "extract" else "Local video path")
        command.add_argument("--output", required=True)
        command.add_argument("--side", choices=("left", "right"), required=True)
        command.add_argument("--tolerance-deg", type=float, default=5.0)
        command.add_argument("--max-gap-s", type=float, default=0.2)
        if name == "video":
            command.add_argument("--markers", required=True, help="HSV marker configuration JSON")
            command.add_argument("--observations-output", help="Optional full per-frame observations JSON")
    args = parser.parse_args(argv)
    try:
        if args.command == "extract":
            data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        else:
            from .video import observe_video
            config = json.loads(Path(args.markers).read_text(encoding="utf-8"))
            data = observe_video(args.input, config)
            if args.observations_output:
                write_json(args.observations_output, data)
        result = extract(data, args.side, args.tolerance_deg, args.max_gap_s)
        write_json(args.output, result)
    except (ValueError, OSError, ImportError) as exc:
        print(f"schikatron: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {args.output}: {result['quality']['sampled_states']}/12 states sampled (projected 2D)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

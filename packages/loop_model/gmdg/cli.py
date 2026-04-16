
from __future__ import annotations
import argparse
import json
import sys
from .models import GeologicalModelGraph
from . import validation

def _cmd_validate(args):
    try:
        model_path = args.model.lower()
        if model_path.endswith(".yaml") or model_path.endswith(".yml"):
            g = GeologicalModelGraph.load_yaml(args.model)
        else:
            g = GeologicalModelGraph.load(args.model)
        validation.validate_all(g)
        print("OK: model is valid")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

def _cmd_schema(args):
    print(json.dumps(GeologicalModelGraph.model_json_schema(), indent=2))
    return 0

def main(argv=None):
    parser = argparse.ArgumentParser(prog="gmdg")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="Validate a GMDG model JSON or YAML file")
    p_val.add_argument("model")
    p_val.set_defaults(func=_cmd_validate)

    p_schema = sub.add_parser("schema", help="Emit JSON Schema for GeologicalModelGraph")
    p_schema.set_defaults(func=_cmd_schema)

    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))

if __name__ == '__main__':
    main()

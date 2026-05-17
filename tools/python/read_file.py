import sys
import json
import os


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No file path provided"}))
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(json.dumps({"success": False, "error": f"File not found: {path}"}))
        sys.exit(1)

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        print(json.dumps({"success": True, "data": {"path": path, "content": content}}))
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()

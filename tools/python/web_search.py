import sys
import json


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "Usage: web_search.py <query> [max_results=5]",
        }))
        sys.exit(1)

    query = sys.argv[1]

    try:
        max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        if max_results < 1 or max_results > 20:
            raise ValueError("max_results must be between 1 and 20")
    except ValueError as exc:
        print(json.dumps({"success": False, "error": f"Invalid argument: {exc}"}))
        sys.exit(1)

    try:
        from ddgs import DDGS
    except ImportError:
        print(json.dumps({"success": False, "error": "ddgs not installed — run: pip install ddgs"}))
        sys.exit(1)

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))

        results = [
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in raw
        ]

        print(json.dumps({
            "success": True,
            "data": {
                "query": query,
                "result_count": len(results),
                "results": results,
            },
        }))

    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()

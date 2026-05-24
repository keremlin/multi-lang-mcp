import sys
import json
import os


def main():
    try:
        import chromadb

        host = os.getenv("CHROMA_HOST", "127.0.0.1")
        port = int(os.getenv("CHROMA_PORT", "8001"))
        client = chromadb.HttpClient(host=host, port=port)

        collections = client.list_collections()
        print(json.dumps({
            "success": True,
            "data": {
                "collections": [{"name": c.name, "metadata": c.metadata} for c in collections]
            },
        }))
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()

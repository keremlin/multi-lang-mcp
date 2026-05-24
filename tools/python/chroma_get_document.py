import sys
import json
import os


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"success": False, "error": "No input provided on stdin"}))
        sys.exit(1)

    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {exc}"}))
        sys.exit(1)

    collection_name = params.get("collection")
    ids = params.get("ids")

    if not collection_name:
        print(json.dumps({"success": False, "error": "Missing required field: collection"}))
        sys.exit(1)
    if not ids or not isinstance(ids, list):
        print(json.dumps({"success": False, "error": "ids must be a non-empty list of strings"}))
        sys.exit(1)

    try:
        import chromadb

        host = os.getenv("CHROMA_HOST", "127.0.0.1")
        port = int(os.getenv("CHROMA_PORT", "8001"))

        client = chromadb.HttpClient(host=host, port=port)
        collection = client.get_collection(name=collection_name)

        results = collection.get(ids=ids, include=["documents", "metadatas"])

        documents = []
        for i, doc_id in enumerate(results["ids"]):
            documents.append({
                "id": doc_id,
                "document": results["documents"][i],
                "metadata": results["metadatas"][i],
            })

        print(json.dumps({
            "success": True,
            "data": {"collection": collection_name, "documents": documents},
        }))
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()

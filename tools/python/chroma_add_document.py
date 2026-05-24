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
    documents = params.get("documents")
    ids = params.get("ids")
    metadatas = params.get("metadatas")
    create_if_missing = params.get("create_if_missing", True)

    if not collection_name:
        print(json.dumps({"success": False, "error": "Missing required field: collection"}))
        sys.exit(1)
    if not documents or not isinstance(documents, list):
        print(json.dumps({"success": False, "error": "documents must be a non-empty list of strings"}))
        sys.exit(1)
    if not ids or not isinstance(ids, list) or len(ids) != len(documents):
        print(json.dumps({"success": False, "error": "ids must be a list of strings with the same length as documents"}))
        sys.exit(1)

    try:
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        host = os.getenv("CHROMA_HOST", "127.0.0.1")
        port = int(os.getenv("CHROMA_PORT", "8001"))
        model = os.getenv("CHROMA_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

        client = chromadb.HttpClient(host=host, port=port)
        ef = SentenceTransformerEmbeddingFunction(model_name=model)

        if create_if_missing:
            collection = client.get_or_create_collection(name=collection_name, embedding_function=ef)
        else:
            collection = client.get_collection(name=collection_name, embedding_function=ef)

        upsert_kwargs = {"documents": documents, "ids": ids}
        if metadatas:
            upsert_kwargs["metadatas"] = metadatas

        collection.upsert(**upsert_kwargs)

        print(json.dumps({
            "success": True,
            "data": {"collection": collection_name, "upserted": len(documents)},
        }))
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()

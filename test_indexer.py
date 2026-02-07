import json
from code_indexer import CodeIndexer
from summary_builder import SummaryBuilder
from ollama_client import OllamaClient


REPO_ID = "sample-repo"
REPO_PATH = r"C:\Harshan's Data\Projects\sample_repo"
OLLAMA_MODEL = "llama3"


def main():
    print("▶ Indexing repository...")
    indexer = CodeIndexer(repo_id=REPO_ID, root_path=REPO_PATH)
    index_json = indexer.index()

    print("▶ Generating summaries with Ollama...")
    ollama_client = OllamaClient(model=OLLAMA_MODEL)
    summarizer = SummaryBuilder(
        index_json=index_json,
        file_sources=indexer.files_source,
        ollama_client=ollama_client
    )

    summarizer.build_all_summaries()

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(index_json, f, indent=2)

    print("✅ Done. Output written to output.json")


if __name__ == "__main__":
    main()

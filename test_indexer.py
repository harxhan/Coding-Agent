import json
from code_indexer import CodeIndexer

REPO_PATH = r"app-Backend"

indexer = CodeIndexer(
    repo_id="habit-tracker-backend",
    root_path=REPO_PATH
)

repo_json = indexer.index()

with open("repo_index_2.json", "w", encoding="utf-8") as f:
    json.dump(repo_json, f, indent=4)

print("Indexing complete. Output written to repo_index_2.json")
"""Push quiz questions to the Hugging Face Hub as datasets."""

import json
from pathlib import Path

from datasets import Dataset
from huggingface_hub import HfApi

ORG_NAME = "context-course"
DATA_DIR = Path(__file__).parent / "data"


def main():
    api = HfApi()

    for file in sorted(DATA_DIR.glob("*.json")):
        with open(file) as f:
            questions = json.load(f)

        dataset = Dataset.from_list(questions)
        repo_id = f"{ORG_NAME}/{file.stem}_quiz"

        print(f"Pushing {len(questions)} questions to {repo_id}...")
        dataset.push_to_hub(repo_id, private=True)
        print(f"  Done: https://huggingface.co/datasets/{repo_id}")


if __name__ == "__main__":
    main()

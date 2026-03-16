from pathlib import Path
import sys

from transformers import AutoTokenizer


BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models" / "intent_model"
TOKENIZER_NAME = "xlm-roberta-base"


def list_model_dir(title: str) -> None:
    print(title)
    if not MODEL_DIR.exists():
        print(f"  Missing directory: {MODEL_DIR}")
        return

    for path in sorted(MODEL_DIR.iterdir(), key=lambda item: item.name.lower()):
        suffix = "/" if path.is_dir() else ""
        print(f"  {path.name}{suffix}")


def main() -> None:
    print(f"Python executable: {sys.executable}")
    print(f"Refreshing tokenizer from: {TOKENIZER_NAME}")
    print(f"Target model directory: {MODEL_DIR}")

    list_model_dir("Files before refresh:")

    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
    tokenizer.save_pretrained(MODEL_DIR)

    list_model_dir("Files after refresh:")

    sentencepiece_path = MODEL_DIR / "sentencepiece.bpe.model"
    print(f"sentencepiece.bpe.model exists: {sentencepiece_path.exists()}")


if __name__ == "__main__":
    main()

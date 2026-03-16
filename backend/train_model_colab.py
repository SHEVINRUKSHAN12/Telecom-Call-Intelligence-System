"""
Colab-friendly intent model training entrypoint.

This keeps the same dataset loading, label encoding, and train/validation
split logic as backend/train_model.py, while making it easy to point model
artifacts at a Google Drive folder in Colab.

Example:
    python backend/train_model_colab.py \
        --model_name xlm-roberta-base \
        --output_dir /content/drive/MyDrive/Telecom-Call-Intelligence-System/models/intent_model_xlmr
"""

import argparse
import json
from pathlib import Path

import torch
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

# Configuration
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "dataset.json"
DEFAULT_OUTPUT_DIR = BASE_DIR / "models" / "intent_model"
DEFAULT_MODEL_NAME = "xlm-roberta-base"

# Training hyperparameters
EPOCHS = 5
BATCH_SIZE = 16
LEARNING_RATE = 2e-5
MAX_LENGTH = 128


class IntentDataset(Dataset):
    """Custom dataset for intent classification."""

    def __init__(self, texts, labels, tokenizer, max_length):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        encoding = self.tokenizer(
            self.texts[idx],
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )

        item = {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": torch.tensor(self.labels[idx], dtype=torch.long),
        }

        # BERT-family models may return token_type_ids while XLM-R does not.
        if "token_type_ids" in encoding:
            item["token_type_ids"] = encoding["token_type_ids"].squeeze(0)

        return item


def load_dataset(path):
    """Load and parse the JSON dataset."""
    print(f"Loading dataset from: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    texts = [item["text"] for item in data]
    labels = [item["label"] for item in data]

    print(f"Loaded {len(texts)} samples")
    return texts, labels


def parse_args():
    """Parse CLI arguments for model selection and output path."""
    parser = argparse.ArgumentParser(
        description="Train an intent classification model in Colab or locally."
    )
    parser.add_argument(
        "--model_name",
        default=DEFAULT_MODEL_NAME,
        help="Hugging Face model name, for example xlm-roberta-base or bert-base-multilingual-cased.",
    )
    parser.add_argument(
        "--output_dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where model, tokenizer, and label_mapping.json will be saved.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    model_name = args.model_name
    output_dir = Path(args.output_dir)

    print("=" * 60)
    print("Intent Classification Model Training")
    print("=" * 60)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    print(f"Dataset path: {DATA_PATH}")
    print(f"Output path: {output_dir}")

    # Load data
    texts, labels = load_dataset(DATA_PATH)

    # Encode labels
    label_encoder = LabelEncoder()
    encoded_labels = label_encoder.fit_transform(labels)
    num_labels = len(label_encoder.classes_)

    print(f"\nLabels found ({num_labels}):")
    for i, label in enumerate(label_encoder.classes_):
        count = sum(1 for current_label in labels if current_label == label)
        print(f"  {i}: {label} ({count} samples)")

    # Split data
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts,
        encoded_labels,
        test_size=0.2,
        random_state=42,
        stratify=encoded_labels,
    )
    print(f"\nTrain size: {len(train_texts)}, Validation size: {len(val_texts)}")

    # Load tokenizer and model
    print(f"\nLoading model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=num_labels,
        id2label={i: label for i, label in enumerate(label_encoder.classes_)},
        label2id={label: i for i, label in enumerate(label_encoder.classes_)},
    )

    # Create datasets
    train_dataset = IntentDataset(train_texts, train_labels, tokenizer, MAX_LENGTH)
    val_dataset = IntentDataset(val_texts, val_labels, tokenizer, MAX_LENGTH)

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        weight_decay=0.01,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        logging_dir=str(output_dir / "logs"),
        logging_steps=50,
        fp16=torch.cuda.is_available(),
        report_to="none",
        seed=42,
    )

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
    )

    print("\n" + "=" * 60)
    print("Starting training...")
    print("=" * 60)
    trainer.train()

    print(f"\nSaving model to: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    label_mapping = {
        "id2label": {i: label for i, label in enumerate(label_encoder.classes_)},
        "label2id": {label: i for i, label in enumerate(label_encoder.classes_)},
    }
    with open(output_dir / "label_mapping.json", "w", encoding="utf-8") as f:
        json.dump(label_mapping, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("Training complete!")
    print("=" * 60)
    print(f"\nModel saved to: {output_dir}")
    print("\nTo use this model in the backend, set:")
    print(f"  INTENT_MODEL_PATH={output_dir}")


if __name__ == "__main__":
    main()

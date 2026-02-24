"""
Train XLM-RoBERTa model for intent classification.

Usage:
    python train_model.py

The script:
1. Loads dataset from backend/data/dataset.json
2. Fine-tunes xlm-roberta-base for classification
3. Saves the model to backend/models/intent_model
"""

import json
import os
from pathlib import Path

import torch
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    DataCollatorWithPadding,
)
from torch.utils.data import Dataset

# Configuration
BASE_DIR = Path(__file__).parent
DATA_PATH = BASE_DIR / "data" / "dataset.json"
OUTPUT_DIR = BASE_DIR / "models" / "intent_model"
MODEL_NAME = "xlm-roberta-base"

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
        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": torch.tensor(self.labels[idx], dtype=torch.long),
        }


def load_dataset(path):
    """Load and parse the JSON dataset."""
    print(f"Loading dataset from: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    texts = [item["text"] for item in data]
    labels = [item["label"] for item in data]
    
    print(f"Loaded {len(texts)} samples")
    return texts, labels


def main():
    print("=" * 60)
    print("Intent Classification Model Training")
    print("=" * 60)
    
    # Check for GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    # Load data
    texts, labels = load_dataset(DATA_PATH)
    
    # Encode labels
    label_encoder = LabelEncoder()
    encoded_labels = label_encoder.fit_transform(labels)
    num_labels = len(label_encoder.classes_)
    
    print(f"\nLabels found ({num_labels}):")
    for i, label in enumerate(label_encoder.classes_):
        count = sum(1 for l in labels if l == label)
        print(f"  {i}: {label} ({count} samples)")
    
    # Split data
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, encoded_labels, test_size=0.2, random_state=42, stratify=encoded_labels
    )
    print(f"\nTrain size: {len(train_texts)}, Validation size: {len(val_texts)}")
    
    # Load tokenizer and model
    print(f"\nLoading model: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=num_labels,
        id2label={i: label for i, label in enumerate(label_encoder.classes_)},
        label2id={label: i for i, label in enumerate(label_encoder.classes_)},
    )
    
    # Create datasets
    train_dataset = IntentDataset(train_texts, train_labels, tokenizer, MAX_LENGTH)
    val_dataset = IntentDataset(val_texts, val_labels, tokenizer, MAX_LENGTH)
    
    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR / "checkpoints"),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        logging_dir=str(OUTPUT_DIR / "logs"),
        logging_steps=50,
        fp16=torch.cuda.is_available(),
        report_to="none",
    )
    
    # Data collator
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)
    
    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
    )
    
    # Train
    print("\n" + "=" * 60)
    print("Starting training...")
    print("=" * 60)
    trainer.train()
    
    # Save model
    print(f"\nSaving model to: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    
    # Save label mapping
    label_mapping = {
        "id2label": {i: label for i, label in enumerate(label_encoder.classes_)},
        "label2id": {label: i for i, label in enumerate(label_encoder.classes_)},
    }
    with open(OUTPUT_DIR / "label_mapping.json", "w") as f:
        json.dump(label_mapping, f, indent=2)
    
    print("\n" + "=" * 60)
    print("Training complete!")
    print("=" * 60)
    print(f"\nModel saved to: {OUTPUT_DIR}")
    print("\nTo use this model, update your .env file:")
    print(f"  INTENT_MODEL_PATH={OUTPUT_DIR}")


if __name__ == "__main__":
    main()

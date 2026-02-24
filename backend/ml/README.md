# ML - Call Intent Classification

This directory contains all machine learning related files for the telecom call classification system.

## Directory Structure

```
ml/
├── data/
│   ├── raw/              # Raw JSON datasets (place your dataset here)
│   └── processed/        # Cleaned & preprocessed datasets for training
├── trained_models/       # Saved model checkpoints and final models
├── scripts/              # Training, evaluation, and inference scripts
└── README.md
```

## Dataset Format

Your JSON dataset should follow this structure for call intent classification:

```json
[
  {
    "text": "I'm having issues with my fiber connection, it keeps disconnecting",
    "label": "Fiber Issue"
  },
  {
    "text": "I want to pay my bill, can you help?",
    "label": "Billing"
  },
  {
    "text": "My PEO TV is not working properly",
    "label": "PEO TV Issue"
  }
]
```

## Supported Labels

- `Fiber Issue`
- `PEO TV Issue`
- `Billing`
- `Complaint`
- `New Connection`
- `General Inquiry`

## Model

We use **XLM-RoBERTa** (xlm-roberta-base) for multilingual text classification, supporting:
- Sinhala
- English
- Mixed-language conversations

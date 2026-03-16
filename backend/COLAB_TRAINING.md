# Colab Training Runbook

These cells assume your Colab session is using a GPU runtime and that this
repository version, including `backend/train_model_colab.py`, is available from
GitHub.

The training script keeps the same dataset loading, label encoding, and
train/validation split logic as `backend/train_model.py`. The dataset is still
read from `backend/data/dataset.json`.

## Cell 1

```python
from google.colab import drive

drive.mount("/content/drive")
```

## Cell 2

```python
%cd /content
!rm -rf /content/Telecom-Call-Intelligence-System
!git clone https://github.com/SHEVINRUKSHAN12/Telecom-Call-Intelligence-System.git
%cd /content/Telecom-Call-Intelligence-System
```

## Cell 3

```python
!pip install -q transformers==4.36.2 accelerate sentencepiece==0.1.99 scikit-learn
```

## Cell 4

```python
import torch

print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
```

## Cell 5

```python
MODEL_NAME = "xlm-roberta-base"
# MODEL_NAME = "bert-base-multilingual-cased"

OUTPUT_DIR = "/content/drive/MyDrive/Telecom-Call-Intelligence-System/models/intent_model_xlmr"
# OUTPUT_DIR = "/content/drive/MyDrive/Telecom-Call-Intelligence-System/models/intent_model_mbert"
```

## Cell 6

```python
!python backend/train_model_colab.py --model_name "$MODEL_NAME" --output_dir "$OUTPUT_DIR"
```

## Cell 7

```python
!ls -lah "$OUTPUT_DIR"
```

## Expected saved files

- `config.json`
- `model.safetensors` or `pytorch_model.bin`
- tokenizer files from `save_pretrained`
- `label_mapping.json`

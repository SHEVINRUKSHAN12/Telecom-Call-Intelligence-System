import os
from dotenv import load_dotenv

load_dotenv()
print(f"INTENT_MODEL_PATH: {os.getenv('INTENT_MODEL_PATH')}")
print(f"Path exists: {os.path.exists(os.getenv('INTENT_MODEL_PATH', ''))}")

from services.classification import predict_intent

# Test with Sinhala telecom text
result = predict_intent("මට fiber connection එකක් ගන්න ඕනේ")
print(f"\nSinhala test: {result['label']} ({result['confidence']:.1%})")
print(f"Model: {result['model']}")
print(f"Scores: {result['scores']}")

# Test with English
result2 = predict_intent("I want to pay my bill and check my balance")
print(f"\nEnglish test: {result2['label']} ({result2['confidence']:.1%})")

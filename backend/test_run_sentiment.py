import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
# Force enable for the script
os.environ["ENABLE_SENTIMENT"] = "true"

from services.sentiment import analyze_sentiment

def test():
    print("Testing sentiment...")
    res = analyze_sentiment("I am very happy with this service!")
    print(f"Result: {res}")

if __name__ == "__main__":
    test()

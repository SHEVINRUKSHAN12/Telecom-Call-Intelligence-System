import requests

# Test health
r = requests.get("http://127.0.0.1:8000/health")
print(f"Health: {r.json()}")

# Test first call with a transcript - check if sentiment is present
r = requests.get("http://127.0.0.1:8000/api/calls")
items = r.json().get("items", [])
for item in items[:3]:
    cid = item["id"][-8:]
    has_preview = bool((item.get("preview") or "").strip())
    has_sent = item.get("sentiment") is not None
    cat = item.get("category", {}).get("label", "?")
    conf = item.get("category", {}).get("confidence", 0)
    print(f"ID:{cid}  preview={has_preview}  sent={has_sent}  cat={cat}  conf={conf:.1%}")

# Now fetch full details for the first call with a transcript
for item in items:
    if (item.get("preview") or "").strip():
        r2 = requests.get(f"http://127.0.0.1:8000/api/calls/{item['id']}")
        full = r2.json()
        print(f"\nFull detail for {item['id'][-8:]}:")
        print(f"  Category: {full.get('category',{}).get('label')} ({full.get('category',{}).get('confidence',0):.1%})")
        print(f"  Sentiment: {full.get('sentiment')}")
        print(f"  Speakers: {len(set(s.get('speaker_label','') for s in full.get('speaker_segments',[])))}")
        break

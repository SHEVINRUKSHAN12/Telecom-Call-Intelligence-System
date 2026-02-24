import requests

r = requests.get("http://127.0.0.1:8000/api/calls")
data = r.json()
items = data.get("items", [])

# Count calls with/without transcripts
with_transcript = [i for i in items if (i.get("preview") or "").strip()]
without_transcript = [i for i in items if not (i.get("preview") or "").strip()]

print(f"Total: {data.get('total')}")
print(f"With transcript: {len(with_transcript)}")
print(f"Without transcript: {len(without_transcript)}")
print()
print("Calls WITH transcript (latest 3):")
for i in with_transcript[:3]:
    print(f"  {i['id'][-8:]}  sent={'Yes' if i.get('sentiment') else 'No'}  cat={i.get('category',{}).get('label','?')}")
print()
print("Calls WITHOUT transcript (latest 3):")
for i in without_transcript[:3]:
    print(f"  {i['id'][-8:]}  sent={'Yes' if i.get('sentiment') else 'No'}  cat={i.get('category',{}).get('label','?')}")

# Check the first call (most recent - what user sees on load)
first = items[0] if items else None
if first:
    print(f"\nFirst call (auto-selected): {first['id'][-8:]}, preview_len={len(first.get('preview','') or '')}")

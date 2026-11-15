import re
from pathlib import Path

batch = Path(
    r"C:\Users\longwen\Desktop\市井文风\诡秘之主-全集\style-analysis\batches\batch-05.md"
).read_text(encoding="utf-8")
shards_dir = Path(r"C:\Users\longwen\Desktop\市井文风\诡秘之主-全集\style-analysis\shards")
shards = {
    i: (shards_dir / f"seg-{i}.txt").read_text(encoding="utf-8", errors="replace")
    for i in range(37, 46)
}

quotes = []
for line in batch.splitlines():
    m = re.search(r"「([^」]+)」", line)
    if m and "｜" in line:
        quotes.append(m.group(1))

seen = set()
unique = []
for q in quotes:
    if q not in seen:
        seen.add(q)
        unique.append(q)

failures = []
for q in unique:
    reasons = []
    if len(q) > 60:
        reasons.append(f"len={len(q)}")
    if "/" in q:
        reasons.append("has_slash")
    hit = [i for i, text in shards.items() if q in text]
    if not hit:
        reasons.append("not_in_shards_37_45")
    if reasons:
        failures.append((q, reasons, hit))

print(f"Total unique quoted examples: {len(unique)}")
print(f"Failures: {len(failures)}")
for q, reasons, hit in failures:
    print("---")
    print("REASON:", ", ".join(reasons))
    disp = q if len(q) <= 50 else q[:47] + "..."
    print("QUOTE:", disp)
    if hit:
        print("PARTIAL hits:", hit)

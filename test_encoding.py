import sys
sys.path.insert(0, 'D:/AI/motor-pm')
from backend_v2.routes.bom import _try_excel, _try_csv, _is_readable

# Simulate user's file hex
hex_str = "00 00 e5 8b 87 65 f6 4e 3a 4e 11 62 f8 53 3a 67 c6 5b 87 65 f6 4e 0c ff 2a 67 cf 7e 41 51 b8 8b 0d 4e ef 53 c5 64 ea 81 69 62 63 65 0c ff 26 54 19 52 06 5c c6 89 3a 4e dd 8f cd 53 a1 8b 97 7b 3a 67 89 5b 68 51 d5 6c 0c ff 7b 98 7f 62 c5 62"
content = bytes.fromhex(hex_str.replace(' ', ''))

print("=== Excel parse ===")
rows = _try_excel(content)
print(f"Excel result: {rows is not None}")

print("\n=== CSV parse ===")
rows = _try_csv(content, "test.csv")
if rows:
    for i, r in enumerate(rows[:5]):
        print(f"  Row {i}: {r}")
else:
    print("  FAILED")

# Also try direct UTF-8 with cleanup
print("\n=== Direct UTF-8 cleanup ===")
text = content.decode('utf-8', errors='replace').replace('\x00', '')
cleaned = []
for c in text:
    cp = ord(c)
    if cp == 0xFFFD: continue
    if c.isprintable() or '一' <= c <= '鿿':
        cleaned.append(c)
    elif c in '\n\r\t,;|':
        cleaned.append(c)
    else:
        cleaned.append(' ')
print(''.join(cleaned)[:200])

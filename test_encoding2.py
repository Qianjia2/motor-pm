# Direct test of encoding logic (inline, not using cached import)
import csv, io

def _is_readable(text):
    if not text: return False
    sample = text[:500]
    if not sample.strip(): return False
    total = max(len(sample), 1)
    good = sum(1 for c in sample if (
        c.isalpha() or c.isdigit() or
        ('一' <= c <= '鿿') or
        c in ' \t\n\r,;.:/-_()（）[]【】<>《》·、。，：；！？"\''
    ))
    if good / total < 0.15: return False
    bad = sum(1 for c in sample if c in '\x00��') + sum(1 for c in sample if 0 < ord(c) < 9)
    if bad / total > 0.25: return False
    return True

def _try_csv(content, filename):
    # Check for UTF-16 BOM
    if content[:2] == b'\xff\xfe':
        text = content[2:].decode('utf-16-le', errors='replace')
    elif content[:2] == b'\xfe\xff':
        text = content[2:].decode('utf-16-be', errors='replace')
    else:
        null_ratio = sum(1 for b in content[:200] if b == 0) / min(200, len(content))
        text = None
        if null_ratio > 0.15:
            for enc in ['utf-16-le', 'utf-16-be']:
                try:
                    text = content.decode(enc)
                    if _is_readable(text): break
                    text = None
                except: continue
        for enc in ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'utf-16']:
            try:
                t2 = content.decode(enc)
                if _is_readable(t2): text = t2; break
            except: continue
        # Last resort: strip null bytes
        if text is None:
            stripped = content.replace(b'\x00', b'')
            for enc in ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']:
                try:
                    text = stripped.decode(enc)
                    if _is_readable(text): break
                    text = None
                except: continue
        # Final fallback: UTF-8 with cleanup
        if text is None:
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
            text = ''.join(cleaned)
            if not _is_readable(text):
                text = None
        if text is None:
            return None

    if not _is_readable(text):
        return None
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    delimiter = '\t' if filename.endswith('.tsv') or '\t' in text[:300] else ','
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        if rows and rows[0]:
            return rows
        return None
    except:
        lines = text.split('\n')
        rows = []
        for line in lines:
            line = line.strip()
            if not line: continue
            try:
                rows.append(list(csv.reader(io.StringIO(line), delimiter=delimiter))[0])
            except: continue
        return rows if rows else None

# Test
hex_str = "00 00 e5 8b 87 65 f6 4e 3a 4e 11 62 f8 53 3a 67 c6 5b 87 65 f6 4e 0c ff 2a 67 cf 7e 41 51 b8 8b 0d 4e ef 53 c5 64 ea 81 69 62 63 65 0c ff 26 54 19 52 06 5c c6 89 3a 4e dd 8f cd 53 a1 8b 97 7b 3a 67 89 5b 68 51 d5 6c 0c ff 7b 98 7f 62 c5 62"
content = bytes.fromhex(hex_str.replace(' ', ''))

rows = _try_csv(content, "test.csv")
print("Result:", "None" if rows is None else f"{len(rows)} rows")
if rows:
    for r in rows[:3]:
        print(" ", r)

# Also test with a real CSV
csv_bytes = "物料编码,物料名称,规格,单位,数量\r\nEM001,永磁体,40x20,个,12".encode('utf-8')
rows2 = _try_csv(csv_bytes, "test.csv")
print("\nReal CSV:", "None" if rows2 is None else f"{len(rows2)} rows")
if rows2:
    for r in rows2:
        print(" ", r)

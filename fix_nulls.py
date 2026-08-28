import sys

with open(sys.argv[1], 'rb') as f:
    data = f.read()

# Replace all null bytes with the escape sequence for source code
data = data.replace(b'\x00', b'\\x00')

with open(sys.argv[1], 'wb') as f:
    f.write(data)

print('Done')

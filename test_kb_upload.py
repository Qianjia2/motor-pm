import urllib.request, json, http.client

login = json.dumps({'username':'admin','password':'admin123'}).encode()
r = urllib.request.urlopen(urllib.request.Request('http://localhost:5002/api/auth/login', login, {'Content-Type':'application/json'}))
token = json.loads(r.read()).get('access_token','')

conn = http.client.HTTPConnection('localhost', 5002)
boundary = '----TestBoundary999'
content = b'Hello World Test'

parts = []
parts.append(f'--{boundary}')
parts.append('Content-Disposition: form-data; name="file"; filename="test.txt"')
parts.append('Content-Type: text/plain')
parts.append('')
parts.append('Hello World Test')
parts.append(f'--{boundary}')
parts.append('Content-Disposition: form-data; name="category"')
parts.append('')
parts.append('')
parts.append(f'--{boundary}--')

body = '\r\n'.join(parts).encode('utf-8')

conn.request('POST', '/api/knowledge/upload', body, {
    'Authorization': 'Bearer ' + token,
    'Content-Type': f'multipart/form-data; boundary={boundary}'
})
resp = conn.getresponse()
data = resp.read().decode()
print(f'Status: {resp.status}')
print(f'Body: {data[:500]}')

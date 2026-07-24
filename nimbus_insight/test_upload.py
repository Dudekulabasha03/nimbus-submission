import requests, json, time

r = requests.get('http://localhost:8000/health')
print('Health:', json.dumps(r.json(), indent=2))

with open('C:/Users/h/Downloads/AutomationEngineer_TakeHome_sample_tickets 1.csv', 'rb') as f:
    up = requests.post('http://localhost:8000/upload', files={'file': ('tickets.csv', f, 'text/csv')})

print('Upload status:', up.status_code)
print('Upload body:', up.json())
if not up.ok:
    exit(1)

job_id = up.json()['job_id']
for i in range(30):
    time.sleep(3)
    s = requests.get(f'http://localhost:8000/status/{job_id}').json()
    print(f'[{i*3}s] Status={s["status"]} Tickets={s.get("ticket_count")}')
    if s['status'] in ('COMPLETED', 'FAILED'):
        err = s.get('error_log') or 'none'
        print('Error log:', err[:400])
        rpt = s.get('report_text') or ''
        print('Report (first 600 chars):', rpt[:600])
        break

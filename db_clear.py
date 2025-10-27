import os, shutil, sqlite3, datetime

DB = os.path.join(os.path.dirname(__file__), 'database1.db')
if not os.path.exists(DB):
    print('ERROR: DB file not found:', DB)
    raise SystemExit(1)

# backup
now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
backup = DB + f'.backup.{now}'
shutil.copy2(DB, backup)
print('BACKUP_CREATED:', backup)

# connect and delete
conn = sqlite3.connect(DB)
cur = conn.cursor()
results = {}
for t in ('order_items','orders','sales'):
    try:
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        before = cur.fetchone()[0]
    except Exception as e:
        before = f'ERROR: {e}'
    try:
        cur.execute(f'DELETE FROM {t}')
        conn.commit()
    except Exception as e:
        print('DELETE ERROR', t, e)
    try:
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        after = cur.fetchone()[0]
    except Exception as e:
        after = f'ERROR: {e}'
    results[t] = (before, after)

conn.close()

print('RESULTS:')
for t, (b,a) in results.items():
    print(f' {t}: before={b}  after={a}')

print('\nDone.')

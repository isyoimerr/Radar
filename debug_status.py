import subprocess, os
log_path = os.path.join(os.getcwd(), 'debug_status.txt')
with open(log_path, 'w', encoding='utf-8') as f:
    f.write('START\n'); f.flush()
    try:
        p = subprocess.run([
            r'C:\Users\ING\Python313\python.exe',
            '-m', 'pytest', 'tests/test_app.py::test_registration_bookmarks_and_auth', '-q', '-rA'
        ], cwd=os.getcwd(), capture_output=True, text=True)
        f.write(f'RETURN {p.returncode}\n')
        f.write(p.stdout)
        f.write(p.stderr)
        f.flush()
    except Exception as exc:
        f.write(f'ERR {type(exc).__name__}: {exc}\n')
        f.flush()

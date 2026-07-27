# Atlas project instructions

## Python environment

For all Python commands and Python tests in this repository, use the project-local virtual environment:

`C:\Users\enesh\Desktop\Projekte - KI\Atlas\.venv\Scripts\python.exe`

From the repository root, prefer:

```powershell
& '.\.venv\Scripts\python.exe' <Argumente>
```

Do not fall back to the Codex-internal Python runtime under
`C:\Users\enesh\.cache\codex-runtimes\...` merely because `python` is not available on the shell `PATH`.

Before reporting a missing Python dependency, verify it using the Atlas `.venv`.

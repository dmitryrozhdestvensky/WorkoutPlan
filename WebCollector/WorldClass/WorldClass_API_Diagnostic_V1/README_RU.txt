WorldClass API Diagnostic V1 (read-only)

This is a standalone diagnostic. It does NOT edit collect_worldclass.py, CSV, SQLite, or PostgreSQL.
It uses the existing Playwright installation in C:\WebCollector\WorldClass\.venv.

Unpack the folder WorldClass_API_Diagnostic_V1 into C:\WebCollector\WorldClass.
In PowerShell:
cd C:\WebCollector\WorldClass
.\.venv\Scripts\python.exe .\WorldClass_API_Diagnostic_V1\diagnose_api.py --clicks 38 --wait 3

Attach the generated file:
C:\WebCollector\WorldClass\WorldClass_API_Diagnostic_V1\worldclass_api_diagnostic_result.json

The script records query parameter names/values (redacting typical secrets), HTTP statuses,
and JSON response shape (keys and list sizes), not trainer records.
Review output for sensitive custom URL parameters before sharing.

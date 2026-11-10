# WebCollector — DataQuality / DaData V1

Python 3.13.17, Windows. **Only reads** `C:\WebCollector\Data\fitness_trainers_master.xlsx`. The original Excel is never written. DaData responses are stored in a separate SQLite checkpoint and reported in a new Excel workbook.

## Installation
Extract the archive folder contents to `C:\WebCollector\DataQuality`. In PowerShell:

```powershell
cd C:\WebCollector\DataQuality
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe dadata_quality.py preview --limit 10
```

## Enter keys ONLY in the CURRENT PowerShell session

```powershell
$secureApi = Read-Host 'DaData API key' -AsSecureString
$secureSecret = Read-Host 'DaData secret key' -AsSecureString
$env:DADATA_API_KEY = [System.Net.NetworkCredential]::new('', $secureApi).Password
$env:DADATA_SECRET_KEY = [System.Net.NetworkCredential]::new('', $secureSecret).Password
Remove-Variable secureApi,secureSecret
```

Keys are not written to code, `.env`, logs, or CSV. They do remain in this PowerShell session's environment until cleared. Do not upload logs or screenshots of secrets.

## First request (uses 1 API request)

```powershell
.\.venv\Scripts\python.exe dadata_quality.py probe
```

## Continue cautiously (99 more requests, at most 100 per newly created checkpoint)

```powershell
.\.venv\Scripts\python.exe dadata_quality.py run --limit 99 --confirm-requests
.\.venv\Scripts\python.exe dadata_quality.py report
```

Do not run the 99-request step before checking current remaining free requests in the DaData dashboard: the 100 free requests are **one-time per account, not per script**. Subsequent calls may be charged. This prototype caps new requests per command but existing previous API usage is not knowable to the script. If you want to test only 10, use `run --limit 10 --confirm-requests`.

## Outputs
- `dadata_quality_progress.sqlite3`: checkpoint; previously processed rows are not requested again.
- `dadata_quality_report.xlsx`: new summary and review tables. **No automatic merging**; identical names do not mean identical people.

## Security and compliance
Only full names are transmitted to DaData, not city, profile URLs, social accounts, or the full workbook. Check data-processing/legal basis before sending personal data to third parties. The service requires email verification and may require account balance after free requests. `qc=0` means recognized confidently; it is **not identity verification**.

## Debug
- HTTP 401: API or secret key invalid.
- HTTP 403: verify email and balance/free quota, keys.
- SSL error: don't disable TLS certificate checks; inspect antivirus proxy/certificates.
- When finished: `Remove-Item Env:DADATA_API_KEY,Env:DADATA_SECRET_KEY -ErrorAction SilentlyContinue`.

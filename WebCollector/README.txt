WEB COLLECTOR: LAPTOP -> MAIN WINDOWS PC
========================================

BEFORE YOU BEGIN
* On both computers close the collectors, Python and any open Excel files.
* The main PC may already have C:\WebCollector. Do NOT delete that directory.
* An Internet connection is not needed for transfer; use a USB stick, network share or cloud drive.

1. ON THE LAPTOP
   Copy 01_EXPORT_LAPTOP.ps1 from this kit onto the laptop.
   In PowerShell:

   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Path\To\01_EXPORT_LAPTOP.ps1"

   A ZIP called WebCollector_Laptop_YYYYMMDD_HHMMSS.zip will be placed on the laptop Desktop.
   The export includes all files under C:\WebCollector EXCEPT .venv, Python caches,
   node_modules, .git, TransferBackups, and certain other generated caches.
   It preserves Data, DDXFitness, SocialEnrichment and their CSV, SQLite, JSON,
   source code and processing history. The exact file manifest and SHA256 hashes
   are stored in the ZIP.

   If the exporter warns that Data/fitness_trainers_master.xlsx is missing,
   do not proceed; locate the up-to-date 2141-row master file first.

2. TRANSFER
   Copy the exported WebCollector_Laptop_*.zip to the main PC
   (for example to the main PC Desktop).
   Copy 02_IMPORT_MAIN_PC.ps1 to the main PC as well.

3. ON THE MAIN PC
   In PowerShell use the actual full path to your ZIP:

   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Path\To\02_IMPORT_MAIN_PC.ps1" -Archive "C:\Users\YOUR_USER\Desktop\WebCollector_Laptop_YYYYMMDD_HHMMSS.zip"

   The importer verifies SHA256 checksums BEFORE touching the existing project.
   It tells you how many files would be replaced. Type YES to continue.
   All old files that are about to be overwritten are copied into
   C:\WebCollector\TransferBackups\YYYYMMDD_HHMMSS\.
   Nothing else in C:\WebCollector is deleted. Files with the same relative path
   are replaced by laptop copies. It verifies every resulting file checksum.

4. AFTER IMPORT
   Check at least:
   C:\WebCollector\Data\fitness_trainers_master.xlsx
   C:\WebCollector\DDXFitness\ddxfitness_trainers.csv
   C:\WebCollector\SocialEnrichment\social_candidates.csv
   C:\WebCollector\SocialEnrichment\social_errors.csv
   C:\WebCollector\SocialEnrichment\social_progress.json (if present)

   Important: Social Enrichment candidates are NOT approved by this transfer.
   Do not run the Social Enrichment --apply option until the links are checked.
   The master workbook should have 2141 trainer rows based on the prior merge.

5. PYTHON ENVIRONMENTS
   Python .venv folders cannot safely be copied across machines.
   On main PC, for a project requiring a new venv (example):
      cd C:\WebCollector\SocialEnrichment
      py -3.13 -m venv .venv
      .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   If a local .venv already works, leave it in place.

TROUBLESHOOTING
   File locked: close Excel/Python and retry.
   Permission error: confirm your user can write to C:\WebCollector.
   If import fails partway, old versions of overwritten files are under
   TransferBackups. Do not run collectors until files are reconciled.

SECURITY
   This kit transfers the COMPLETE WebCollector working folder. Review it for
   private credentials, secrets, access tokens and personal data before sharing
   the resulting ZIP via third-party cloud services.

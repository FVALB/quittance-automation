# TODO — Quittance de Loyer Automation

## Phase 0: GCP & Auth Setup (one-time, manual)

- [ ] Go to https://console.cloud.google.com and create a new project named `quittance-automation`
- [ ] In "APIs & Services → Library", enable all four APIs:
  - Google Drive API
  - Google Sheets API
  - Google Docs API
  - Gmail API
- [ ] Go to "APIs & Services → OAuth consent screen"
  - User type: External
  - App name: `Quittance Automation`
  - Support email + developer email: your Gmail address
  - On the "Test Users" screen: add your own Gmail address
  - Save
- [ ] Go to "APIs & Services → Credentials → + Create Credentials → OAuth client ID"
  - Application type: **Desktop app**
  - Name: `Quittance Desktop Client`
  - Download the JSON → rename it to `client_secret.json`
  - Place it in the `credentials/` folder of this project
- [ ] Copy `.env.example` to `.env` and fill in:
  - `TEMPLATE_FILE_ID` — from the Drive URL of your Word template
  - `SPREADSHEET_ID` — from the Google Sheets URL
  - `LANDLORD_EMAIL` — your Gmail address
  - `TRIGGER_DAY` and `PAYMENT_DAY` as needed
- [ ] Note: the `Link Folder` column in the sheet must contain the **folder ID** only,
      not the full URL. Extract it from: `drive.google.com/drive/folders/FOLDER_ID`
- [ ] Set up virtual environment and install dependencies:
  ```
  python -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  ```
- [ ] Run first-time OAuth authorization (opens browser):
  ```
  python -c "from src.auth import get_credentials; get_credentials()"
  ```
  After signing in and clicking Allow, `credentials/token.json` is created automatically.

---

## Phase 1: Testing (run in order)

- [ ] Test date computation:
  ```
  python -c "from src.date_utils import compute_dates_for_month; import datetime; print(compute_dates_for_month(datetime.date(2026, 2, 5)))"
  ```
  Expected: `{'year': '2026', 'month': '02', 'month_description': 'Février', 'last_day': '28'}`

- [ ] Test sheet read:
  ```
  python -c "
  from src.auth import get_credentials, build_services
  from src.sheets import read_tenant_rows
  import os; from dotenv import load_dotenv; load_dotenv()
  svc = build_services(get_credentials())
  tenants = read_tenant_rows(svc['sheets'], os.getenv('SPREADSHEET_ID'))
  for t in tenants: print(t['Name'], t['Surname'], t['Email'])
  "
  ```

- [ ] Run dry-run end-to-end (no emails sent, no Drive files created):
  ```
  python main.py --dry-run
  ```
  Check `logs/quittance.log` — all 4 tenants should appear as `[DRY RUN]`.
  An alert email IS sent (to verify Gmail API works) with `DRY RUN` in the subject.

- [ ] Live test with one tenant (temporarily set one email to your own address in the sheet):
  ```
  python main.py
  ```
  Verify:
  - PDF appears in tenant Drive folder with correct name
  - Email received with PDF attached
  - Summary email received at LANDLORD_EMAIL
  - `processed_months.json` contains the current `YYYY-MM` key
  - Temp Google Doc is deleted from Drive

- [ ] Idempotency test — run again immediately:
  ```
  python main.py
  ```
  Expected: exits with "Already processed YYYY-MM" message. No duplicate files or emails.

---

## Phase 2: Windows Task Scheduler Setup (one-time, manual)

- [ ] Open Task Scheduler → "Create Task" (not "Create Basic Task")
- [ ] **General tab**:
  - Name: `Quittance de Loyer - Monthly Generation`
  - Check: "Run whether user is logged on or not"
  - Check: "Run with highest privileges"
- [ ] **Triggers tab** → New:
  - Begin the task: On a schedule → Monthly
  - Months: all 12
  - Day: match your `TRIGGER_DAY` value in `.env`
  - Time: 08:00:00 (or preferred time)
- [ ] **Actions tab** → New → Start a program:
  - Program: `C:\Users\felip\Documents\Dev\Quittance Automation\.venv\Scripts\python.exe`
  - Arguments: `main.py`
  - Start in: `C:\Users\felip\Documents\Dev\Quittance Automation`
- [ ] **Conditions tab**: Uncheck "Start only if on AC power"
- [ ] **Settings tab**:
  - Restart on failure: every 1 hour, up to 3 times
  - Stop task if it runs longer than: 1 hour
- [ ] Test: right-click the task → Run → check Last Run Result (should be `0x0`)

---

## Future Improvements (not in initial scope)

- [ ] Add `--month YYYY-MM` flag to regenerate a past month's receipts
- [ ] Add `--force` flag to bypass the idempotency check
- [ ] Before uploading, check if a PDF with the same name already exists in the tenant folder
- [ ] Store `TEMPLATE_FILE_ID` in a "Config" sheet tab so everything is managed from one place

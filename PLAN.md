# Quittance de Loyer — Approved Automation Plan

> This is the plan that was designed and approved before implementation.
> It captures the full context, decisions, and rationale for the project.

---

## Context

The landlord (Christian Felipe VALENCIA BAQUERO) generates French rent receipts ("Quittances de loyer") monthly for 4 tenants. Currently this is a manual process. This automation will:
- Read tenant data from a Google Sheet
- Fill a Word template stored in Google Drive with each tenant's info
- Export the result as a PDF (entirely via Google APIs — no local Word/LibreOffice needed)
- Email each tenant their receipt via Gmail
- Store a copy of each PDF in the tenant's dedicated Google Drive folder
- Send a run summary/alert email to the landlord
- Run automatically on a configurable day each month via Windows Task Scheduler

**Key constraints confirmed:**
- Local Windows PC (Task Scheduler trigger)
- No Microsoft Word or LibreOffice installed → PDF export done via Google Drive API
- Gmail API with OAuth 2.0 (Desktop app flow)
- GCP project must be created from scratch
- Trigger day ≠ payment date (both set in `.env`)
- Partial failure: skip failing tenant, continue others, include in alert
- PDF name: `Quittance de Loyer MM YYYY - Name SURNAME.pdf`

---

## 1. Project Folder Structure

```
Quittance Automation/
│
├── credentials/                     # Git-ignored
│   ├── client_secret.json           # Downloaded from GCP Console
│   └── token.json                   # Auto-generated on first auth run
│
├── logs/                            # Git-ignored
│   └── quittance.log                # RotatingFileHandler output
│
├── src/
│   ├── __init__.py
│   ├── auth.py                      # OAuth 2.0 flow + token refresh
│   ├── config.py                    # Load & validate .env
│   ├── date_utils.py                # Auto-compute French month names / last day
│   ├── sheets.py                    # Read tenants + write auto-dates back to sheet
│   ├── drive.py                     # copy template / export PDF / upload / delete
│   ├── docs.py                      # batchUpdate ReplaceAllText for placeholders
│   ├── gmail.py                     # Send receipt + alert emails
│   ├── idempotency.py               # processed_months.json read/write
│   ├── validator.py                 # Required-field checks per tenant row
│   └── orchestrator.py             # Main pipeline; partial failure logic
│
├── main.py                          # Entry point: argparse --dry-run, logging, calls orchestrator
├── .env                             # Secrets (git-ignored)
├── .env.example                     # Committed template with placeholder values
├── requirements.txt
├── processed_months.json            # Idempotency tracker (git-ignored)
├── PLAN.md                          # This file
├── TODO.md
├── .gitignore
└── README.md
```

---

## 2. Template Placeholders (from the Word template)

The Word template uses `{{double-brace}}` syntax:

| Placeholder | Source |
|---|---|
| `{{Name}}` | Sheet: Name |
| `{{Surname}}` | Sheet: Surname |
| `{{Month Description}}` | Auto-computed (French month name) |
| `{{Year}}` | Auto-computed |
| `{{Month}}` | Auto-computed (zero-padded) |
| `{{Last day}}` | Auto-computed (last day of month) |
| `{{Payment day}}` | `.env`: PAYMENT_DAY |
| `{{Net rent}}` | Sheet: Net rent |
| `{{Charges}}` | Sheet: Charges |
| `{{Total rent}}` | Sheet: Total rent |
| `{{Rent description}}` | Sheet: Rent description |

---

## 3. Core Processing Flow

```
1. Idempotency check → skip if month already processed
2. OAuth authenticate → get Drive / Sheets / Docs / Gmail services
3. Read all tenant rows from Google Sheet
4. Auto-compute dates (Year, Month, Month Description, Last day)
5. Write computed dates back to sheet (keeps sheet up-to-date)
6. FOR EACH tenant:
   a. Validate required fields
   b. Build {{replacements}} dict
   c. Copy Word template in Drive (auto-converts to Google Docs)
   d. batchUpdate: ReplaceAllText for all placeholders
   e. Export Google Doc as PDF bytes (Drive files.export)
   f. Upload PDF bytes to tenant's Drive folder
   g. Send receipt email to tenant (Gmail API, PDF attached)
   h. Delete temp Google Doc
   i. On any failure: log + continue, add to failures list
7. Send summary alert email to landlord
8. Mark month as processed in processed_months.json
```

---

## 4. GCP Setup Steps (One-Time)

### 4.1 Create Project
1. Go to https://console.cloud.google.com
2. New Project → name: `quittance-automation`

### 4.2 Enable APIs
In "APIs & Services → Library", enable:
- Google Drive API
- Google Sheets API
- Google Docs API
- Gmail API

### 4.3 OAuth Consent Screen
1. "APIs & Services → OAuth consent screen"
2. User type: **External**
3. App name: `Quittance Automation`
4. Support + developer email: your Gmail
5. On **Test Users** screen: add your own Gmail address
6. Save

### 4.4 Create OAuth Credentials
1. "APIs & Services → Credentials → + Create Credentials → OAuth client ID"
2. Application type: **Desktop app**
3. Name: `Quittance Desktop Client`
4. Download JSON → rename to `client_secret.json` → place in `credentials/`

### 4.5 First-Run Authorization
```bash
python -c "from src.auth import get_credentials; get_credentials()"
```
Browser opens → sign in → Allow. `credentials/token.json` is created. All subsequent runs use the cached token (auto-refreshed).

---

## 5. Windows Task Scheduler Setup

1. Open Task Scheduler → "Create Task" (not Basic Task)
2. **General**: Name = `Quittance de Loyer - Monthly Generation`; "Run whether user logged on or not"; "Run with highest privileges"
3. **Triggers**: Monthly → all months → day = value of `TRIGGER_DAY` env var → time `08:00:00`
4. **Actions**: Start a program
   - Program: `C:\Users\felip\Documents\Dev\Quittance Automation\.venv\Scripts\python.exe`
   - Arguments: `main.py`
   - Start in: `C:\Users\felip\Documents\Dev\Quittance Automation`
5. **Conditions**: Uncheck "only if AC power" (laptop safety)
6. **Settings**: Restart on failure every 1h, max 3 times; stop if runs > 1h

---

## 6. `.env` Variables

```dotenv
# Google Drive
TEMPLATE_FILE_ID=           # File ID of the Word template
SPREADSHEET_ID=             # Google Sheet ID
SHEET_RANGE=Sheet1!A2:N     # Data range (adjust tab name if needed)

# Scheduling
TRIGGER_DAY=5               # Day Task Scheduler fires (matches task config)
PAYMENT_DAY=5               # Day written into receipt as payment date

# Landlord
LANDLORD_EMAIL=you@gmail.com

# Paths
CLIENT_SECRET_PATH=credentials/client_secret.json
TOKEN_PATH=credentials/token.json
PROCESSED_MONTHS_PATH=processed_months.json
LOG_FILE=logs/quittance.log
LOG_LEVEL=INFO
```

**Note on `Link Folder` column in sheet**: must contain the Google Drive **folder ID** only (not the full URL).
Extract from: `drive.google.com/drive/folders/FOLDER_ID_HERE`

---

## 7. Python Dependencies

```
google-api-python-client==2.154.0
google-auth==2.37.0
google-auth-oauthlib==1.2.1
google-auth-httplib2==0.2.0
python-dotenv==1.0.1
tenacity==9.0.0
```

Install:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## 8. Error Handling Strategy

| Layer | Catches | Response |
|---|---|---|
| `tenacity` retry | HTTP 429, 500, 503; network timeouts | Exponential backoff, 3 attempts |
| Per-tenant `try/except` | Any exception for one tenant | Skip tenant, log, continue rest |
| `validator.py` | Missing/empty required fields | Raises `ValueError` before any API call |
| Top-level in `main.py` | Auth failure, sheet unreadable | Sends alert email, exits code 1 |

**Specific cases:**
- **Token expired**: auto-refreshed by `google-auth`. If refresh fails (revoked), re-run manually to re-authorize via browser.
- **Placeholder not found in doc**: `batchUpdate` makes 0 replacements silently. Raw `{{placeholder}}` text appears in PDF — visible in the alert email.
- **Tenant Drive folder ID invalid**: `HttpError 404` on upload. Caught per-tenant, included in failure summary.
- **`processed_months.json` corrupt**: treated as missing; overwritten with fresh data.

---

## 9. Improvements Included in This Implementation

| Improvement | Rationale |
|---|---|
| **Idempotency** (`processed_months.json`) | Prevents duplicate receipts if task fires twice or user runs manually |
| **Dry-run mode** (`--dry-run`) | Safe testing without sending emails or creating Drive files |
| **Retry + backoff** (`tenacity`) | Google APIs rate-limit; transient failures should auto-recover |
| **Data validation before API calls** | Avoids wasted API quota and orphan temp files in Drive |
| **Auto-date computation** | Landlord never manually updates Year/Month/LastDay in the sheet |
| **Configurable tenant list** | Sheet row count drives tenant count; no code change when tenants change |

**Future improvements (not in initial scope):**
- `--month YYYY-MM` flag to regenerate receipts for a past month
- `--force` flag to bypass the idempotency check
- Detect existing PDF in tenant folder before uploading (Drive-level idempotency)
- Store `TEMPLATE_FILE_ID` in a "Config" sheet tab so everything is managed from one place

---

## 10. Verification Checklist

```
[ ] Test date computation:
    python -c "from src.date_utils import compute_dates_for_month; import datetime; print(compute_dates_for_month(datetime.date(2026, 2, 5)))"
    → {'Year': '2026', 'Month': '02', 'Month Description': 'Février', 'Last day': '28'}

[ ] Test OAuth flow (first run — opens browser):
    python -c "from src.auth import get_credentials; get_credentials()"
    → credentials/token.json created

[ ] Test sheet read:
    python -c "
    from src.auth import get_credentials, build_services
    from src.sheets import read_tenant_rows
    import os; from dotenv import load_dotenv; load_dotenv()
    svc = build_services(get_credentials())
    tenants = read_tenant_rows(svc['sheets'], os.getenv('SPREADSHEET_ID'))
    for t in tenants: print(t['Name'], t['Surname'], t['Email'])
    "
    → 4 tenant names printed

[ ] Dry-run end-to-end (no emails, no Drive files):
    python main.py --dry-run
    → All 4 tenants logged as [DRY RUN]
    → Alert email sent with "DRY RUN" in subject

[ ] Live test with one tenant (use your own email in the sheet):
    python main.py
    → PDF in tenant Drive folder with correct filename
    → Email received with PDF attached
    → Summary email received at LANDLORD_EMAIL
    → processed_months.json contains current YYYY-MM key
    → Temp Google Doc deleted from Drive

[ ] Idempotency test (run again same month):
    python main.py
    → "Already processed YYYY-MM" log message, exits immediately

[ ] Task Scheduler test:
    Right-click task → Run
    → Last Run Result = 0x0
    → logs/quittance.log shows full run output
```

---

## 11. Decisions Made During Planning

| Question | Decision |
|---|---|
| Where does the script run? | Local Windows PC + Task Scheduler |
| Google auth method? | OAuth 2.0 Desktop app (browser flow, token cached) |
| Gmail sending method? | Gmail API (same OAuth credentials) |
| Trigger day vs payment date? | Different — both configurable in `.env` |
| No Word/LibreOffice installed — PDF conversion? | Google Drive API `files.export` (server-side) |
| If one tenant fails? | Skip, continue others, include in alert email |
| PDF filename format? | `Quittance de Loyer MM YYYY - Name SURNAME.pdf` |
| Completion alerts? | Email to landlord's Gmail |
| GCP starting point? | From scratch (full setup walkthrough included) |

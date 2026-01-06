# MainCRM Scripts

## Setup

```bash
cd Docs/SePersonalCRM/MainCRM/Scripts
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
```

## Telegram (quick commands)

```bash
cd Docs/SePersonalCRM/MainCRM/Scripts
source venv/bin/activate

# Find user_id / handle candidates:
python3 telegram_find_handles.py --person "Name" --search --query "SearchTerm"

# Save handle + user_id into Context/sync_list_telegram.txt:
python3 telegram_find_handles.py --person "Name" --save "@username" --user-id 12345678

# Sync one person:
python3 telegram_sync.py --person "Name"

# Sync all #DO_SYNC:
python3 telegram_sync.py --all --report report.txt

# Inbox sync:
python3 telegram_inbox_sync.py
```


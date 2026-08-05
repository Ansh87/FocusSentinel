# The two-way SMS/Twilio feature (student texts to request time, parent
# replies YES/NO) was removed at the product owner's request in favor of an
# email-based approve/deny flow (see app/routers/extension_requests.py's
# GET /decide endpoint). This file is no longer imported anywhere
# (see app/main.py) and is left as an inert placeholder only because this
# sandbox can't delete files on the mounted project folder -- safe to
# delete for real via `git rm services/api/app/routers/sms.py`.

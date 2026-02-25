# PythonAnywhere Deployment (Paid SaaS)

This project now includes:

- A production WSGI app: `wsgi.py` -> `trainer.webapp:create_app()`
- Stripe subscription billing + webhook handling
- Login via one-time email codes (Mailgun)
- Secure session cookies and protected trainer routes
- Existing trainer functionality preserved behind auth

## 1) What You Need To Do Personally

1. Create a Stripe product + recurring price (monthly/yearly).
2. Create a Mailgun sending domain/API key.
3. Create your PythonAnywhere web app and set environment variables.
4. Point Stripe webhook to your deployed URL.
5. Add custom domain + SSL in PythonAnywhere.

## 2) Stripe Setup

1. In Stripe Dashboard:
   - Create product: `Poker Trainer`.
   - Create recurring price and copy `price_...` value.
2. Get API keys:
   - `STRIPE_SECRET_KEY` (live key for production).
3. Create webhook endpoint:
   - URL: `https://<your-domain>/api/billing/webhook`
   - Events:
     - `checkout.session.completed`
     - `customer.subscription.created`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
     - `invoice.paid`
     - `invoice.payment_failed`
   - Copy signing secret `whsec_...` -> `STRIPE_WEBHOOK_SECRET`.

### Stripe Sandbox: Exact Click Path (Beginner Walkthrough)

Use these steps while your Dashboard says `sandbox`:

1. Create the subscription product/price:
   - Go to `Product catalog` -> `+ Create product`.
   - Name: `Poker Trainer`.
   - Pricing: `Recurring`.
   - Amount: your test amount (for example `29.00` USD).
   - Billing period: `Monthly`.
   - Click `Add product`.
   - Open the product, click `Add another price`, create a yearly recurring price if you want one.
2. Copy price IDs:
   - Open the created price row and copy the ID that starts with `price_`.
   - This project currently uses one checkout price at a time:
     - `STRIPE_PRICE_ID=<price_...>`
3. Copy secret API key:
   - Go to `Developers` -> `API keys`.
   - Reveal/copy `Secret key` in sandbox (starts with `sk_test_`).
   - Set:
     - `STRIPE_SECRET_KEY=<sk_test_...>` (for sandbox testing)
4. Create webhook destination:
   - Go to `Developers` -> `Workbench` -> `Webhooks`.
   - Click `Add destination`.
   - Scope: `Your account`.
   - API version: leave default.
   - Select events:
     - `checkout.session.completed`
     - `customer.subscription.created`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
     - `invoice.paid`
     - `invoice.payment_failed`
   - Destination type: `Webhook endpoint (URL)`.
   - Endpoint URL: `https://<your-domain>/api/billing/webhook`
   - Click `Create destination`.
   - On the destination details page, copy signing secret (starts with `whsec_`) and set:
     - `STRIPE_WEBHOOK_SECRET=<whsec_...>`
5. Configure customer portal:
   - Go to `Settings` -> `Billing` -> `Customer portal`.
   - Turn on at least:
     - `Cancel subscription`
     - `Payment methods`
     - `Invoice history`
   - If you want plan switching later, enable `Switch plan` and map allowed products/prices.
   - Save changes.
   - In sandbox, preview/test from a test customer:
     - `Customers` -> pick customer -> `Actions` -> `Open customer portal`.

### Where Stripe Values Go In This Project

Set these environment variables in PythonAnywhere WSGI config (see section 5):

- `STRIPE_SECRET_KEY` = Stripe secret API key (`sk_test_...` for sandbox, `sk_live_...` for production)
- `STRIPE_PRICE_ID` = recurring subscription price ID (`price_...`)
- `STRIPE_WEBHOOK_SECRET` = webhook signing secret (`whsec_...`)

These are loaded by:

- `trainer/webapp.py` (`_load_billing_config`)
- Used in checkout + webhook handling in `trainer/billing.py`

## 3) Mailgun Setup

1. Verify your sending domain (for example `mg.yourdomain.com`).
2. Create API key.
3. Use:
   - `MAILGUN_API_KEY`
   - `MAILGUN_DOMAIN`
   - `MAILGUN_FROM_EMAIL` (for example `Poker Trainer <noreply@mg.yourdomain.com>`)

### Mailgun Sandbox: Exactly What To Copy

From your screenshot, Mailgun is showing:

- `API Key` (hidden in UI) -> use as `MAILGUN_API_KEY`
- `Sandbox domain` (looks like `sandbox...mailgun.org`) -> use as `MAILGUN_DOMAIN`
- Base URL is already built into this app (`https://api.mailgun.net`) so you do not set it.

For sandbox testing, set:

- `MAILGUN_DOMAIN=sandboxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.mailgun.org`
- `MAILGUN_FROM_EMAIL=Poker Trainer <postmaster@sandboxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.mailgun.org>`

Important sandbox limitation:

- Mailgun sandbox can only send to authorized recipient emails.
- In Mailgun, add your own email under `Authorized recipients` before testing login codes.

### Do I Add My PythonAnywhere Domain To Mailgun?

No, not for this integration.

- Mailgun domain = the sending email domain (`sandbox...mailgun.org` in test, `mg.yourdomain.com` in production).
- PythonAnywhere domain is your app/webhook host and belongs in app config, not Mailgun config.

## 4) PythonAnywhere First-Time Deploy

In a Bash console:

```bash
git clone <your-repo-url>
cd poker_analyzer
mkvirtualenv --python=/usr/bin/python3.10 poker-analyzer
pip install -r requirements/production.txt
```

Generate secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Add environment variables to your virtualenv `postactivate`:

```bash
vi $VIRTUAL_ENV/bin/postactivate
```

Copy values from `.env.production.example` and set real secrets.

Then load env and initialize DB tables (auto-created on first run):

```bash
source $VIRTUAL_ENV/bin/postactivate
python -c "from trainer.webapp import create_app; create_app(); print('ok')"
```

## 5) PythonAnywhere Web Tab (WSGI)

1. Add Web App -> **Manual configuration** (same Python version as venv).
2. Set Virtualenv path to your `poker-analyzer` env.
3. Edit WSGI file and use:

```python
import os
import sys

path = "/home/<your-username>/poker_analyzer"
if path not in sys.path:
    sys.path.append(path)

os.environ["TRAINER_ENV"] = "production"
os.environ["TRAINER_REQUIRE_AUTH"] = "1"
os.environ["TRAINER_SECRET_KEY"] = "<same secret>"
os.environ["TRAINER_PUBLIC_BASE_URL"] = "https://<your-domain>"
os.environ["TRAINER_ALLOWED_HOSTS"] = "<your-domain>,www.<your-domain>,<yourusername>.pythonanywhere.com"
os.environ["TRAINER_FORCE_HTTPS"] = "1"
os.environ["TRAINER_COOKIE_SECURE"] = "1"
os.environ["TRAINER_DB_PATH"] = "/home/<your-username>/poker_analyzer/trainer/data/trainer.db"
os.environ["STRIPE_SECRET_KEY"] = "sk_live_..."
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_..."
os.environ["STRIPE_PRICE_ID"] = "price_..."
os.environ["MAILGUN_API_KEY"] = "key-..."
os.environ["MAILGUN_DOMAIN"] = "mg.yourdomain.com"
os.environ["MAILGUN_FROM_EMAIL"] = "Poker Trainer <noreply@mg.yourdomain.com>"

from wsgi import application
```

4. Reload web app.

## 6) Verify In Browser

1. Open `https://<your-domain>/login`.
2. Click `Start Subscription` and complete Stripe checkout.
3. After redirect, app should open `/setup.html`.
4. Log out and test `Email Login Code`.
5. Test `Manage Billing`.

## 7) Security Checklist (Production)

- `TRAINER_ENV=production`
- `TRAINER_REQUIRE_AUTH=1`
- `TRAINER_SECRET_KEY` is long random value
- `TRAINER_FORCE_HTTPS=1`
- `TRAINER_COOKIE_SECURE=1`
- `TRAINER_ALLOWED_HOSTS` includes only your domains
- `TRAINER_EXPOSE_LOGIN_CODES=0`
- Stripe webhook secret is set
- Mailgun sender domain is verified

## 8) Future Deployments

In Bash:

```bash
workon poker-analyzer
cd ~/poker_analyzer
git pull
pip install -r requirements/production.txt
```

Then hit **Reload** in PythonAnywhere Web tab.

import re
import time
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import case

from app.database import get_db
from app import models

import os

router = APIRouter()

FREE_MODE_FLAG = "free_mode.flag"
FREE_MODE_USERNAME = "tenant-free"
FREE_MODE_PASSWORD = "tenant-free"


def free_mode_page():
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Connected</title>
        <style>
            body {{
                margin: 0;
                background: #FFFFFF;
                color: #1A1A1A;
                font-family: 'Inter', sans-serif;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 32px 16px;
                text-align: center;
            }}
            .box {{
                max-width: 380px;
            }}
            h1 {{
                font-size: 24px;
                margin-bottom: 12px;
            }}
            p {{
                color: #6B6B6B;
                font-size: 15px;
            }}
        </style>
    </head>
    <body>
        <div class="box">
            <h1>You're connected</h1>
            <p>This network is provided free for tenants.</p>
        </div>

        <form id="auto-login-form" action="http://192.168.88.1/login" method="post" style="display:none;">
            <input type="hidden" name="dst" value="http://www.msftconnecttest.com/redirect">
            <input type="hidden" name="username" value="{FREE_MODE_USERNAME}">
            <input type="hidden" name="password" value="{FREE_MODE_PASSWORD}">
        </form>
        <script>
            document.getElementById('auto-login-form').submit();
        </script>
    </body>
    </html>
    """


# --- Password recovery ("text me my password") ----------------------------
#
# A customer who paid but never saw/received their password types the phone
# number they paid with, and we TEXT the password to that number. We never
# show it on screen: phone numbers aren't secret, so showing it would let
# anyone who knows a tenant's number read their password. Texting it means
# only the person holding that SIM receives it.
#
# Rate limits are deliberately per phone number, not per IP: every tenant
# reaches this server through the plot's single public IP, so a tight
# per-IP limit would lock all of them out together.
RECOVERY_PER_PHONE_LIMIT = 3        # requests per phone number per window
RECOVERY_PER_PHONE_WINDOW = 3600    # seconds
RECOVERY_MIN_GAP = 60               # seconds between requests for one number
RECOVERY_PER_IP_LIMIT = 40          # loose flood guard only (shared IP!)
RECOVERY_PER_IP_WINDOW = 600
RECOVERY_SMS_LIMIT = 80             # SMS actually sent per window, all numbers
RECOVERY_SMS_WINDOW = 3600          # (protects the gateway phone's SIM credit)
KENYA_UTC_OFFSET = timedelta(hours=3)

_recovery_hits = {}
_recovery_lock = threading.Lock()


def _allow(key, limit, window, min_gap=0, record=True):
    """Sliding-window limiter. Returns True if allowed (and records the hit
    unless record=False). In-memory: resets if the app restarts."""
    now = time.time()
    with _recovery_lock:
        stamps = [t for t in _recovery_hits.get(key, []) if now - t < window]
        too_many = len(stamps) >= limit
        too_soon = bool(min_gap) and bool(stamps) and (now - stamps[-1] < min_gap)
        blocked = too_many or too_soon
        if not blocked and record:
            stamps.append(now)
        _recovery_hits[key] = stamps
        if len(_recovery_hits) > 5000:  # keep memory bounded
            for k in [k for k, v in _recovery_hits.items()
                      if not v or now - v[-1] > 7200]:
                del _recovery_hits[k]
        return not blocked


def _normalize_phone(raw):
    """Any common way of typing a Kenyan mobile number -> 2547XXXXXXXX /
    2541XXXXXXXX, or None if it isn't one."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("254"):
        pass
    elif len(digits) == 10 and digits.startswith("0"):
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "71":
        digits = "254" + digits
    else:
        return None
    return digits if digits[3] in "71" else None


class PasswordRequest(BaseModel):
    phone: str


RECOVERY_REPLY = {
    "ok": True,
    "message": (
        "If this number has an active package, we've texted the password "
        "to it. It can take up to a minute to arrive."
    ),
}


def _send_recovery_sms(phone, password, expires_at):
    # The SMS service is imported here, not at the top of the file, on
    # purpose: if it ever breaks (missing package, bad credentials) only
    # this feature fails -- the payment page and logins keep working.
    try:
        from app.services.android_sms_service import AndroidSMSService
        expiry = (expires_at + KENYA_UTC_OFFSET).strftime("%d %b %Y, %I:%M %p")
        result = AndroidSMSService().send_password_sms(phone, password, expiry)
        if result is None:
            print(f"[recovery] SMS gateway rejected/failed for {phone}")
    except Exception as e:
        print(f"[recovery] SMS failed for {phone}: {e}")


@router.post("/request-password")
def request_password(
    body: PasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    phone = _normalize_phone(body.phone)
    if not phone:
        raise HTTPException(
            status_code=400,
            detail="Enter a valid Kenyan phone number, e.g. 0712345678.",
        )

    # Every request counts against these limits whether or not the number
    # is a customer, so a 429 reveals nothing about who has an account.
    ip = request.client.host if request.client else "unknown"
    if not _allow(f"ip:{ip}", RECOVERY_PER_IP_LIMIT, RECOVERY_PER_IP_WINDOW):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a few minutes.")
    if not _allow(f"ph:{phone}", RECOVERY_PER_PHONE_LIMIT, RECOVERY_PER_PHONE_WINDOW, min_gap=RECOVERY_MIN_GAP):
        raise HTTPException(
            status_code=429,
            detail="A password was already requested for this number a moment ago. Please wait a minute, or contact us on WhatsApp.",
        )
    if not _allow("sms", RECOVERY_SMS_LIMIT, RECOVERY_SMS_WINDOW, record=False):
        raise HTTPException(status_code=429, detail="We're busy right now. Please try again shortly, or contact us on WhatsApp.")

    # Older accounts were sometimes saved without the 254 prefix, so match
    # the common stored forms of the same number.
    candidates = {phone, phone[3:], "0" + phone[3:]}
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # The password on the router is the one from the most recent activation.
    # Activations stack onto the customer's remaining time, so the payment
    # with the latest expiry is the most recently activated one.
    payment = (
        db.query(models.Payment)
        .join(models.Customer)
        .filter(models.Customer.phone.in_(candidates))
        .filter(models.Payment.activated == True)
        .filter(models.Payment.hotspot_password != None)
        .filter(models.Payment.hotspot_password != "")
        .filter(models.Payment.expires_at != None)
        .filter(models.Payment.expires_at > now)
        .order_by(models.Payment.expires_at.desc())
        .first()
    )

    if payment and _allow("sms", RECOVERY_SMS_LIMIT, RECOVERY_SMS_WINDOW):
        # Sent in the background so the reply is instant (and identical)
        # whether or not the number matched anything.
        background.add_task(
            _send_recovery_sms, phone, payment.hotspot_password, payment.expires_at
        )

    return RECOVERY_REPLY


@router.get("/lookup-login/{code}")
def lookup_login(code: str, db: Session = Depends(get_db)):
    payment = (
        db.query(models.Payment)
        .filter(models.Payment.hotspot_password == code)
        .filter(models.Payment.activated == True)
        .order_by(models.Payment.paid_at.desc())
        .first()
    )
    if not payment:
        return {"found": False}
    return {"found": True, "username": payment.customer.phone}


@router.get("/pay", response_class=HTMLResponse)
def payment_page(db: Session = Depends(get_db)):
    if os.path.exists(FREE_MODE_FLAG):
        return HTMLResponse(content=free_mode_page())

    packages = (
        db.query(models.Package)
        .filter(models.Package.active == True)
        .order_by(
            case((models.Package.name == "Admin Apology Offer", 0), else_=1),
            models.Package.id
        )
        .all()
    )

    def signal_bars(pkg):
        speeds = [int("".join(filter(str.isdigit, p.download_speed)) or 0) for p in packages]
        max_speed = max(speeds) if speeds else 1
        this_speed = int("".join(filter(str.isdigit, pkg.download_speed)) or 0)
        level = max(1, round((this_speed / max_speed) * 4)) if max_speed else 1

        bars = ""
        for i in range(4):
            active = "active" if i < level else ""
            height = 8 + (i * 6)
            bars += f'<div class="bar {active}" style="height:{height}px"></div>'
        return bars

    package_cards = ""
    for pkg in packages:
        package_cards += f"""
        <button class="package" onclick="pay({pkg.id}, this)">
            <div class="package-top">
                <span class="package-name">{pkg.name}</span>
                <div class="bars">{signal_bars(pkg)}</div>
            </div>
            <div class="package-speed">{pkg.download_speed} / {pkg.upload_speed}</div>
            <div class="package-price">KES {int(pkg.price)}</div>
        </button>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="format-detection" content="telephone=no">
        <title>Shadow WiFi</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #FFFFFF;
                --surface: #FFF5EB;
                --surface-hover: #FFE8D1;
                --text: #1A1A1A;
                --muted: #6B6B6B;
                --accent: #E8792D;
                --accent-text: #FFFFFF;
                --border: #FFD9B3;
            }}

            * {{ box-sizing: border-box; }}

            body {{
                margin: 0;
                background: var(--bg);
                color: var(--text);
                font-family: 'Inter', sans-serif;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                padding: 32px 16px;
            }}

            .container {{
                width: 100%;
                max-width: 420px;
            }}

            .logo-card {{
                background: #ffffff;
                border-radius: 16px;
                padding: 16px;
                display: flex;
                justify-content: center;
                margin-bottom: 24px;
            }}

            .logo-card img {{
                max-width: 140px;
                height: auto;
                display: block;
            }}

            .eyebrow {{
                font-family: 'IBM Plex Mono', monospace;
                font-size: 12px;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: var(--accent);
                margin-bottom: 8px;
            }}

            h1 {{
                font-family: 'Space Grotesk', sans-serif;
                font-size: 28px;
                font-weight: 700;
                margin: 0 0 24px 0;
                line-height: 1.2;
            }}

            .tabs {{
                display: flex;
                gap: 4px;
                background: var(--surface);
                border-radius: 10px;
                padding: 4px;
                margin-bottom: 24px;
            }}

            .tab {{
                flex: 1;
                text-align: center;
                padding: 10px;
                border-radius: 7px;
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
                color: var(--muted);
                border: none;
                background: transparent;
                font-family: 'Inter', sans-serif;
            }}

            .tab.active {{
                background: var(--accent);
                color: var(--accent-text);
            }}

            .panel {{ display: none; }}
            .panel.active {{ display: block; }}

            label {{
                display: block;
                font-size: 13px;
                color: var(--muted);
                margin-bottom: 8px;
            }}

            input {{
                width: 100%;
                padding: 14px 16px;
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 10px;
                color: var(--text);
                font-family: 'IBM Plex Mono', monospace;
                font-size: 16px;
                margin-bottom: 16px;
            }}

            input:focus {{
                outline: none;
                border-color: var(--accent);
            }}

            .package {{
                width: 100%;
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 18px;
                margin-bottom: 12px;
                cursor: pointer;
                text-align: left;
                color: var(--text);
                transition: background 0.15s ease, border-color 0.15s ease;
            }}

            .package:hover {{
                background: var(--surface-hover);
                border-color: var(--accent);
            }}

            .package-top {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }}

            .package-name {{
                font-family: 'Space Grotesk', sans-serif;
                font-weight: 500;
                font-size: 16px;
            }}

            .bars {{
                display: flex;
                align-items: flex-end;
                gap: 3px;
                height: 26px;
            }}

            .bar {{
                width: 5px;
                background: var(--border);
                border-radius: 2px;
            }}

            .bar.active {{
                background: var(--accent);
            }}

            .package-speed {{
                font-family: 'IBM Plex Mono', monospace;
                font-size: 13px;
                color: var(--muted);
                margin-bottom: 6px;
            }}

            .package-price {{
                font-family: 'IBM Plex Mono', monospace;
                font-size: 20px;
                font-weight: 500;
                color: var(--accent);
            }}

            button.primary {{
                width: 100%;
                padding: 14px;
                background: var(--accent);
                color: var(--accent-text);
                border: none;
                border-radius: 10px;
                font-family: 'Space Grotesk', sans-serif;
                font-weight: 700;
                font-size: 15px;
                cursor: pointer;
            }}

            .trial-box {{
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 20px;
                text-align: center;
            }}

            .trial-box p {{
                color: var(--muted);
                font-size: 14px;
                margin-bottom: 16px;
            }}

            a.trial-link {{
                display: block;
                width: 100%;
                padding: 14px;
                background: var(--accent);
                color: var(--accent-text);
                border-radius: 10px;
                font-family: 'Space Grotesk', sans-serif;
                font-weight: 700;
                font-size: 15px;
                text-decoration: none;
                text-align: center;
                box-sizing: border-box;
            }}

            #status {{
                display: none;
                position: fixed;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                max-width: 380px;
                width: calc(100% - 32px);
                padding: 16px;
                background: var(--surface);
                border: 1px solid var(--accent);
                border-radius: 10px;
                font-size: 14px;
                color: var(--text);
                font-family: 'IBM Plex Mono', monospace;
                z-index: 100;
                box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            }}

            #status.visible {{ display: block; }}

            #status.success {{ color: var(--accent); }}

            .note {{
                margin-top: 16px;
                font-size: 13px;
                color: var(--muted);
                line-height: 1.5;
            }}

            .link-btn {{
                background: none;
                border: none;
                padding: 0;
                color: var(--accent);
                font: inherit;
                font-weight: 500;
                text-decoration: underline;
                cursor: pointer;
            }}

            #recover-box {{
                display: none;
                margin-top: 14px;
                padding: 16px;
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 12px;
            }}

            #recover-box.open {{ display: block; }}

            .contact {{
                margin-top: 32px;
                padding-top: 20px;
                border-top: 1px solid var(--border);
                text-align: center;
            }}

            .contact p {{
                color: var(--muted);
                font-size: 13px;
                margin-bottom: 12px;
            }}

            .contact-links {{
                display: flex;
                gap: 10px;
                justify-content: center;
            }}

            .contact-link {{
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 10px 16px;
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 10px;
                color: var(--text);
                text-decoration: none;
                font-size: 13px;
                font-weight: 500;
            }}

            .contact-link:hover {{
                border-color: var(--accent);
            }}

            .contact p.contact-numbers {{
                margin: 14px 0 0;
                font-family: 'IBM Plex Mono', monospace;
                font-size: 14px;
                color: var(--text);
                letter-spacing: 0.02em;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo-card">
                <img src="/static/logo.jpeg" alt="Shadownet">
            </div>

            <div class="eyebrow">Shadow WiFi</div>
            <h1>Get connected.</h1>

            <div id="main-ui">
            <div class="tabs">
                <button class="tab active" onclick="showTab('buy')">Buy</button>
                <button class="tab" onclick="showTab('login')">Log In</button>
            </div>

            <div id="panel-buy" class="panel active">
                <div id="package-list">
                    {package_cards}
                </div>

                <div id="phone-step" style="display:none;">
                    <label for="phone">Enter your phone number to pay</label>
                    <input type="tel" id="phone" placeholder="0743512704" />
                    <button class="primary" onclick="confirmPay()">Pay Now</button>
                </div>

                <p class="note">Paid but didn't get your password? Open the <button type="button" class="link-btn" onclick="openRecovery()">Log In tab</button> and request it with your phone number. We'll text it to you.</p>
            </div>

            <div id="panel-login" class="panel">
                <form id="login-form" onsubmit="return handleManualLogin(event)">
                    <label for="login-password">Password</label>
                    <input type="text" id="login-password" name="password" placeholder="e.g. H7NKX4T9Q2" required>
                    <button type="submit" class="primary">Log In</button>
                </form>

                <p class="note">Don't have your password? <button type="button" class="link-btn" onclick="toggleRecovery()">Request it with your phone number</button> and we'll text it to you.</p>

                <div id="recover-box">
                    <label for="recover-phone">Phone number you paid with</label>
                    <input type="tel" id="recover-phone" placeholder="0712345678" autocomplete="tel">
                    <button type="button" class="primary" id="recover-btn" onclick="requestPassword()">Text me my password</button>
                </div>
            </div>
            </div>

            <p id="status"></p>

            <div class="contact">
                <p>Need help?</p>
                <div class="contact-links">
                    <a href="https://wa.me/254743512704" class="contact-link">WhatsApp</a>
                </div>
                <p class="contact-numbers">0745136987 / 0743512704</p>
            </div>
        </div>

        <script>
            function toggleRecovery() {{
                const box = document.getElementById('recover-box');
                box.classList.toggle('open');
                if (box.classList.contains('open')) {{
                    document.getElementById('recover-phone').focus();
                }}
            }}

            function openRecovery() {{
                showTab('login');
                document.getElementById('recover-box').classList.add('open');
                document.getElementById('recover-phone').focus();
            }}

            async function requestPassword() {{
                const phone = document.getElementById('recover-phone').value.trim();
                const status = document.getElementById('status');
                const btn = document.getElementById('recover-btn');

                if (!phone) {{
                    status.innerText = "Enter the phone number you paid with.";
                    status.className = "visible";
                    return;
                }}

                btn.disabled = true;
                status.innerText = "Sending...";
                status.className = "visible";

                try {{
                    const res = await fetch('/request-password', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ phone: phone }})
                    }});
                    const data = await res.json();

                    if (res.ok) {{
                        status.innerText = data.message;
                        status.className = "visible success";
                        // Allow another request after a minute (the server enforces this too).
                        setTimeout(() => {{ btn.disabled = false; }}, 60000);
                    }} else {{
                        status.innerText = (typeof data.detail === "string") ? data.detail : "Something went wrong. Try again.";
                        status.className = "visible";
                        btn.disabled = false;
                    }}
                }} catch (err) {{
                    status.innerText = "Network error. Check your connection and try again.";
                    status.className = "visible";
                    btn.disabled = false;
                }}
            }}

            function autoLogin(username, password) {{
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = 'http://192.168.88.1/login';
                form.innerHTML = `
                    <input type="hidden" name="username" value="${{username}}">
                    <input type="hidden" name="password" value="${{password}}">
                    <input type="hidden" name="dst" value="http://www.msftconnecttest.com/redirect">
                `;
                document.body.appendChild(form);
                form.submit();
            }}
            async function handleManualLogin(event) {{
                event.preventDefault();

                const passwordInput = document.getElementById('login-password');
                const code = passwordInput.value.trim();
                const status = document.getElementById('status');
                const submitBtn = event.target.querySelector('button[type="submit"]');

                if (!code) {{
                    status.innerText = "Enter your password first.";
                    status.className = "visible";
                    return false;
                }}

                submitBtn.disabled = true;
                status.innerText = "Checking your details...";
                status.className = "visible";

                try {{
                    const res = await fetch(`/lookup-login/${{encodeURIComponent(code)}}`);
                    const data = await res.json();

                    if (!data.found) {{
                        status.innerText = "That password wasn't recognized. Please check it and try again.";
                        status.className = "visible";
                        submitBtn.disabled = false;
                        return false;
                    }}

                    autoLogin(data.username, code);
                }} catch (err) {{
                    status.innerText = "Network error. Check your connection and try again.";
                    status.className = "visible";
                    submitBtn.disabled = false;
                }}

                return false;
            }}
            function showTab(name) {{
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
                document.querySelector(`.tab[onclick="showTab('${{name}}')"]`).classList.add('active');
                document.getElementById(`panel-${{name}}`).classList.add('active');
            }}

            let selectedPackageId = null;

            function pay(packageId, btn) {{
                selectedPackageId = packageId;
                document.getElementById('package-list').style.display = 'none';
                document.getElementById('phone-step').style.display = 'block';
            }}

            async function confirmPay() {{
                const phone = document.getElementById("phone").value.trim();
                const status = document.getElementById("status");

                if (!phone) {{
                    status.innerText = "Enter your phone number first.";
                    status.className = "visible";
                    return;
                }}

                status.innerText = "Sending request to your phone...";
                status.className = "visible";

                try {{
                    const response = await fetch(`/paystack/pay?package_id=${{selectedPackageId}}&phone_number=${{encodeURIComponent(phone)}}`, {{
                        method: "POST"
                    }});
                    const data = await response.json();
                    const paymentId = data.payment_id;
                    const statusToken = data.status_token;

                    if (response.ok) {{
                        status.innerHTML = "Check your phone and enter your M-Pesa PIN to complete payment.";
                        status.className = "visible success";

                        pollForActivation(paymentId, statusToken, status);
                    }} else {{
                        status.innerText = data.message || "Something went wrong. Try again.";
                        status.className = "visible";
                    }}
                }} catch (err) {{
                    status.innerText = "Network error. Check your connection and try again.";
                    status.className = "visible";
                }}
            }}

            function pollForActivation(paymentId, statusToken, status) {{
                let attempts = 0;
                const interval = setInterval(async () => {{
                    attempts++;
                    const res = await fetch(`/paystack/status/${{paymentId}}?t=${{encodeURIComponent(statusToken || "")}}`);
                    const data = await res.json();

                    if (data.activated) {{
                        clearInterval(interval);
                        status.innerHTML = `
                            ✅ Payment successful! Connecting you now...<br><br>
                            <small>If it doesn't connect automatically, use:<br>
                            Username: <b>${{data.username}}</b> — Password: <b>${{data.password}}</b></small>
                        `;
                        autoLogin(data.username, data.password);
                    }} else if (attempts > 20) {{
                        clearInterval(interval);
                        status.innerHTML = "Still waiting for payment confirmation. If you completed payment, please contact us.";
                    }}
                }}, 3000);
            }}
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html)

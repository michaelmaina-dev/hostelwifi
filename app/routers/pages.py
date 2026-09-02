from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

router = APIRouter()


@router.get("/pay", response_class=HTMLResponse)
def payment_page(db: Session = Depends(get_db)):
    packages = db.query(models.Package).filter(models.Package.active == True).all()

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
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo-card">
                <img src="/static/logo.jpeg" alt="Shadownet">
            </div>

            <div class="eyebrow">Shadow WiFi</div>
            <h1>Get connected.</h1>

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
            </div>

            <div id="panel-login" class="panel">
                <form action="http://192.168.88.1/login" method="post" onsubmit="return normalizeLoginPhone()">
                    <input type="hidden" name="dst" value="http://www.msftconnecttest.com/redirect">
                    <label for="login-username">Phone number</label>
                    <input type="text" id="login-username" name="username" placeholder="0743512704" required>
                    <label for="login-password">Password</label>
                    <input type="text" id="login-password" name="password" placeholder="e.g. QGH7XXXXX" required>
                    <button type="submit" class="primary">Log In</button>
                </form>
            </div>

            <p id="status"></p>

            <div class="contact">
                <p>Need help?</p>
                <div class="contact-links">
                    <a href="https://wa.me/254743512704" class="contact-link">WhatsApp</a>
                    <a href="tel:+254743512704" class="contact-link">Call</a>
                </div>
            </div>
        </div>

        <script>
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
            function normalizeLoginPhone() {{
                const input = document.getElementById('login-username');
                let phone = input.value.trim();
                if (phone.startsWith('+')) phone = phone.slice(1);
                if (phone.startsWith('0')) phone = '254' + phone.slice(1);
                input.value = phone;
                return true;
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

                    if (response.ok) {{
                        status.innerHTML = "Check your phone and enter your M-Pesa PIN to complete payment.";
                        status.className = "visible success";

                        pollForActivation(paymentId, status);
                    }} else {{
                        status.innerText = data.message || "Something went wrong. Try again.";
                        status.className = "visible";
                    }}
                }} catch (err) {{
                    status.innerText = "Network error. Check your connection and try again.";
                    status.className = "visible";
                }}
            }}

            function pollForActivation(paymentId, status) {{
                let attempts = 0;
                const interval = setInterval(async () => {{
                    attempts++;
                    const res = await fetch(`/paystack/status/${{paymentId}}`);
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

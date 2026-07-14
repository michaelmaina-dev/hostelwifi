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
        # crude speed ranking just to size the bars — highest download in the list gets full bars
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
                --bg: #14161C;
                --surface: #1D2027;
                --surface-hover: #262A33;
                --text: #F2F0EA;
                --muted: #8A8F9C;
                --accent: #E8A33D;
                --accent-dim: #4A3A1E;
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
                margin: 0 0 28px 0;
                line-height: 1.2;
            }}

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
                border: 1px solid #333842;
                border-radius: 10px;
                color: var(--text);
                font-family: 'IBM Plex Mono', monospace;
                font-size: 16px;
                margin-bottom: 28px;
            }}

            input:focus {{
                outline: none;
                border-color: var(--accent);
            }}

            .package {{
                width: 100%;
                background: var(--surface);
                border: 1px solid #2A2E37;
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

            .package:focus-visible {{
                outline: 2px solid var(--accent);
                outline-offset: 2px;
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
                background: #3A3F4A;
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

            #status {{
                margin-top: 20px;
                font-size: 14px;
                color: var(--muted);
                min-height: 20px;
                font-family: 'IBM Plex Mono', monospace;
            }}

            #status.success {{ color: var(--accent); }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="eyebrow">Shadow WiFi</div>
            <h1>Pick a package,<br>pay with M-Pesa.</h1>

            <label for="phone">Phone number</label>
            <input type="tel" id="phone" placeholder="0743512704" />

            {package_cards}

            <p id="status"></p>
        </div>

        <script>
            async function pay(packageId, btn) {{
                const phone = document.getElementById("phone").value.trim();
                const status = document.getElementById("status");

                if (!phone) {{
                    status.innerText = "Enter your phone number first.";
                    status.className = "";
                    return;
                }}

                btn.disabled = true;
                status.innerText = "Sending request to your phone...";
                status.className = "";

                try {{
                    const response = await fetch(`/mpesa/pay?package_id=${{packageId}}&phone_number=${{encodeURIComponent(phone)}}`, {{
                        method: "POST"
                    }});
                    const data = await response.json();
                    status.innerText = data.message || "Something went wrong. Try again.";
                    status.className = response.ok ? "success" : "";
                }} catch (err) {{
                    status.innerText = "Network error. Check your connection and try again.";
                }} finally {{
                    btn.disabled = false;
                }}
            }}
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html)
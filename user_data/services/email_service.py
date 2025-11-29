import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from connectify_bulk_hiring.settings import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD


def send_professional_mail(to_email: str, subject: str, body: str, company_name: str):
    """
    Sends a beautiful, formal, modern HTML email.
    """

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject

    # Highly professional, premium HTML template
    html_content = f"""
    <html>
    <head>
        <style>
            body {{
                background: #f0f2f5;
                margin: 0;
                padding: 0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
            .container {{
                max-width: 650px;
                margin: auto;
                background: #ffffff;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            }}
            .header {{
                background: linear-gradient(135deg, #4b79ff, #6f9bff);
                padding: 30px 25px;
                color: #ffffff;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 26px;
                font-weight: 600;
            }}
            .content {{
                padding: 25px 30px;
                color: #333333;
                font-size: 16px;
                line-height: 1.7;
            }}
            .content p {{
                margin: 0 0 15px;
            }}
            .footer {{
                margin-top: 30px;
                background: #fafafa;
                padding: 18px 25px;
                text-align: center;
                font-size: 13px;
                color: #777777;
                border-top: 1px solid #eeeeee;
            }}
            .footer a {{
                color: #4b79ff;
                text-decoration: none;
            }}
        </style>
    </head>

    <body>
        <div class="container">

            <div class="header">
                <h1>{subject}</h1>
            </div>

            <div class="content">
                <p>{body}</p>

                <br><br>
                <p style="color: #555; font-size: 15px;">
                    Regards,<br><br>
                    <strong style="font-size: 16px;">{company_name}</strong><br>
                    Hiring Team
                </p>
            </div>

            <div class="footer">
                This is an automated email. Please do not reply directly.<br>
                © {2025} {company_name}. All rights reserved.
            </div>

        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(html_content, "html"))

    # Send Email
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print("Failed to send email:", str(e))

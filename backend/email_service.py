"""
LumiVeil — Email Service
========================
Sends transactional emails via Resend API.
Docs: https://resend.com/docs/api-reference/emails/send-email

Emails sent:
  - Email verification on signup
  - Password reset
"""

import os
import requests

RESEND_API_KEY  = os.environ.get('RESEND_API_KEY', '')
FROM_EMAIL      = 'LumiVeil <onboarding@resend.dev>'
WEBSITE_URL     = 'https://himanshubhandari2196.github.io/LumiVeil'
BACKEND_URL     = 'https://lumiveil-api-production-8706.up.railway.app'


def _send_email(to, subject, html):
    """Send an email via Resend. Returns True on success."""
    if not RESEND_API_KEY:
        print(f'[Email] RESEND_API_KEY not set — skipping email to {to}')
        return False
    try:
        resp = requests.post(
            'https://api.resend.com/emails',
            headers={
                'Authorization': f'Bearer {RESEND_API_KEY}',
                'Content-Type':  'application/json'
            },
            json={
                'from':    FROM_EMAIL,
                'to':      [to],
                'subject': subject,
                'html':    html
            },
            timeout=10
        )
        if resp.status_code in (200, 201):
            return True
        print(f'[Email] Resend error {resp.status_code}: {resp.text[:200]}')
        return False
    except Exception as e:
        print(f'[Email] Exception: {e}')
        return False


def send_verification_email(to_email, verification_token):
    """Send the email verification link after signup."""
    verify_url = f'{BACKEND_URL}/api/v1/auth/verify-email?token={verification_token}'

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#0C0C10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0C0C10;padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">

          <!-- Logo -->
          <tr>
            <td align="center" style="padding-bottom:32px;">
              <span style="font-size:20px;font-weight:700;color:#7C6FF7;">👁 LumiVeil</span>
            </td>
          </tr>

          <!-- Card -->
          <tr>
            <td style="background:#17171E;border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:40px 36px;">
              <h1 style="margin:0 0 12px;font-size:24px;font-weight:600;color:#fff;letter-spacing:-0.5px;">
                Verify your email
              </h1>
              <p style="margin:0 0 28px;font-size:15px;color:#9490A8;line-height:1.6;">
                Thanks for signing up! Click the button below to verify your email address and activate your LumiVeil account.
              </p>
              <a href="{verify_url}"
                 style="display:inline-block;background:#7C6FF7;color:#fff;text-decoration:none;
                        font-size:15px;font-weight:600;padding:14px 32px;border-radius:10px;">
                Verify email address
              </a>
              <p style="margin:28px 0 0;font-size:13px;color:#9490A8;line-height:1.6;">
                This link expires in <strong style="color:#fff;">24 hours</strong>. 
                If you didn't create a LumiVeil account, you can safely ignore this email.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td align="center" style="padding-top:24px;">
              <p style="margin:0;font-size:12px;color:rgba(255,255,255,0.25);">
                LumiVeil · Lift the veil on fake content ·
                <a href="{WEBSITE_URL}" style="color:rgba(255,255,255,0.4);">lumiveil.app</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return _send_email(to_email, 'Verify your LumiVeil email address', html)


def send_password_reset_email(to_email, reset_token):
    """Send the password reset link."""
    reset_url = f'{WEBSITE_URL}?reset_token={reset_token}'

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#0C0C10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0C0C10;padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">

          <!-- Logo -->
          <tr>
            <td align="center" style="padding-bottom:32px;">
              <span style="font-size:20px;font-weight:700;color:#7C6FF7;">👁 LumiVeil</span>
            </td>
          </tr>

          <!-- Card -->
          <tr>
            <td style="background:#17171E;border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:40px 36px;">
              <h1 style="margin:0 0 12px;font-size:24px;font-weight:600;color:#fff;letter-spacing:-0.5px;">
                Reset your password
              </h1>
              <p style="margin:0 0 28px;font-size:15px;color:#9490A8;line-height:1.6;">
                We received a request to reset your LumiVeil password. Click the button below to choose a new one.
              </p>
              <a href="{reset_url}"
                 style="display:inline-block;background:#7C6FF7;color:#fff;text-decoration:none;
                        font-size:15px;font-weight:600;padding:14px 32px;border-radius:10px;">
                Reset password
              </a>
              <p style="margin:28px 0 0;font-size:13px;color:#9490A8;line-height:1.6;">
                This link expires in <strong style="color:#fff;">1 hour</strong>. 
                If you didn't request a password reset, you can safely ignore this email — your password won't change.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td align="center" style="padding-top:24px;">
              <p style="margin:0;font-size:12px;color:rgba(255,255,255,0.25);">
                LumiVeil · Lift the veil on fake content ·
                <a href="{WEBSITE_URL}" style="color:rgba(255,255,255,0.4);">lumiveil.app</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return _send_email(to_email, 'Reset your LumiVeil password', html)

"""
Email notifications for DOR page monitor changes.
Uses Resend API to send change summaries to the configured email.
"""

import logging
from config import settings

logger = logging.getLogger(__name__)


def send_change_notification(changes: list[dict], crawl_stats: dict) -> bool:
    """Send an email summarizing detected changes from a monitor crawl.

    Args:
        changes: List of change dicts with keys: url, type/change_type, title, summary, id
        crawl_stats: Stats dict from run_full_crawl with pages_crawled, etc.

    Returns:
        True if email sent successfully.
    """
    if not settings.RESEND_API_KEY or not settings.NOTIFICATION_EMAIL:
        logger.warning("Resend API key or notification email not configured, skipping notification")
        return False

    if not changes:
        logger.info("No changes to notify about")
        return False

    import resend
    resend.api_key = settings.RESEND_API_KEY

    app_url = settings.APP_URL.rstrip("/")
    monitor_url = f"{app_url}/monitor"

    # Build HTML email
    subject = f"DOR Monitor: {len(changes)} change{'s' if len(changes) != 1 else ''} detected"

    change_rows = ""
    for c in changes:
        change_type = c.get("type") or c.get("change_type", "UNKNOWN")
        title = c.get("title") or c.get("url", "Unknown page")
        url = c.get("url", "")
        summary = c.get("summary", "")
        change_id = c.get("id", "")
        detected_at = c.get("detected_at", "")
        last_modified = c.get("last_modified", "")

        # Format timestamp — prefer server Last-Modified, fall back to detected_at
        timestamp_html = ""
        from datetime import datetime as _dt
        if last_modified:
            try:
                # HTTP Last-Modified format: "Sat, 14 Feb 2026 01:19:34 GMT"
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(last_modified)
                timestamp_html = f'<span style="color: #9ca3af; font-size: 11px; float: right;">Updated {dt.strftime("%b %d, %Y at %I:%M %p")} UTC</span>'
            except Exception:
                try:
                    # ISO format from <time> tags: "2026-02-13T12:00:00Z"
                    dt = _dt.fromisoformat(last_modified.replace("Z", "+00:00"))
                    timestamp_html = f'<span style="color: #9ca3af; font-size: 11px; float: right;">Updated {dt.strftime("%b %d, %Y at %I:%M %p")} UTC</span>'
                except Exception:
                    timestamp_html = f'<span style="color: #9ca3af; font-size: 11px; float: right;">Updated {last_modified}</span>'
        elif detected_at:
            try:
                dt = _dt.fromisoformat(detected_at.replace("Z", "+00:00"))
                timestamp_html = f'<span style="color: #9ca3af; font-size: 11px; float: right;">Detected {dt.strftime("%b %d, %Y at %I:%M %p")} UTC</span>'
            except Exception:
                timestamp_html = f'<span style="color: #9ca3af; font-size: 11px; float: right;">Detected {detected_at[:19]}</span>'

        if change_type == "NEW":
            badge_color = "#059669"
            badge_text = "NEW"
        elif change_type == "MODIFIED":
            badge_color = "#d97706"
            badge_text = "MODIFIED"
        else:
            badge_color = "#6b7280"
            badge_text = change_type

        change_rows += f"""
        <tr>
          <td style="padding: 12px 16px; border-bottom: 1px solid #e5e7eb;">
            {timestamp_html}
            <span style="display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; color: white; background: {badge_color}; margin-right: 8px;">{badge_text}</span>
            <strong style="color: #111827;">{title}</strong>
            <br>
            <a href="{url}" style="color: #6b7280; font-size: 12px; text-decoration: none;">{url}</a>
            {f'<br><span style="color: #6b7280; font-size: 13px;">{summary}</span>' if summary else ''}
          </td>
        </tr>
        """

    pages_crawled = crawl_stats.get("pages_crawled", 0)
    pages_unchanged = crawl_stats.get("pages_unchanged", 0)
    pages_error = crawl_stats.get("pages_error", 0)
    new_wtds = crawl_stats.get("new_wtds_found", 0)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f9fafb; padding: 20px;">
      <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; border: 1px solid #e5e7eb; overflow: hidden;">

        <div style="background: #111827; padding: 20px 24px;">
          <h1 style="color: white; font-size: 18px; margin: 0;">DOR Page Monitor</h1>
          <p style="color: #9ca3af; font-size: 13px; margin: 4px 0 0 0;">{len(changes)} change{'s' if len(changes) != 1 else ''} detected</p>
        </div>

        <div style="padding: 16px 24px;">
          <div style="display: flex; gap: 16px; margin-bottom: 16px;">
            <div style="display: inline-block; padding: 8px 16px; background: #f3f4f6; border-radius: 6px; text-align: center; margin-right: 8px;">
              <div style="font-size: 20px; font-weight: 700; color: #111827;">{pages_crawled}</div>
              <div style="font-size: 11px; color: #6b7280;">Pages Checked</div>
            </div>
            <div style="display: inline-block; padding: 8px 16px; background: #fef3c7; border-radius: 6px; text-align: center; margin-right: 8px;">
              <div style="font-size: 20px; font-weight: 700; color: #92400e;">{len(changes)}</div>
              <div style="font-size: 11px; color: #92400e;">Changes</div>
            </div>
            <div style="display: inline-block; padding: 8px 16px; background: #f3f4f6; border-radius: 6px; text-align: center; margin-right: 8px;">
              <div style="font-size: 20px; font-weight: 700; color: #111827;">{pages_unchanged}</div>
              <div style="font-size: 11px; color: #6b7280;">Unchanged</div>
            </div>
            {f'''<div style="display: inline-block; padding: 8px 16px; background: #dbeafe; border-radius: 6px; text-align: center;">
              <div style="font-size: 20px; font-weight: 700; color: #1e40af;">{new_wtds}</div>
              <div style="font-size: 11px; color: #1e40af;">New WTDs</div>
            </div>''' if new_wtds > 0 else ''}
          </div>
        </div>

        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td style="padding: 8px 16px; background: #f9fafb; font-size: 12px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #e5e7eb;">
              Changes Pending Review
            </td>
          </tr>
          {change_rows}
        </table>

        <div style="padding: 20px 24px; text-align: center;">
          <a href="{monitor_url}" style="display: inline-block; padding: 10px 24px; background: #111827; color: white; border-radius: 6px; text-decoration: none; font-size: 14px; font-weight: 500;">
            Review Changes
          </a>
          <p style="color: #9ca3af; font-size: 12px; margin-top: 8px;">
            Approve changes to add them to your knowledge base
          </p>
        </div>

        <div style="padding: 12px 24px; background: #f9fafb; border-top: 1px solid #e5e7eb;">
          <p style="color: #9ca3af; font-size: 11px; margin: 0; text-align: center;">
            RAG Platform DOR Monitor &mdash; Automated daily scan
          </p>
        </div>
      </div>
    </body>
    </html>
    """

    try:
        result = resend.Emails.send({
            "from": "DOR Monitor <onboarding@resend.dev>",
            "to": [settings.NOTIFICATION_EMAIL],
            "subject": subject,
            "html": html,
        })
        logger.info(f"Notification email sent: {result}")
        return True
    except Exception as e:
        logger.error(f"Failed to send notification email: {e}")
        return False

"""
EventCompanion v2 (single-file) — Commands-first + Dynamic UI JSON + Map Pin Location
------------------------------------------------------------------------------------
A Telegram event management bot (Organizer + Participant) using:
- python-telegram-bot v20+ (async)
- SQLite (WAL)

Dynamic UI:
- STRINGS_FILE (strings.json) contains:
  - commands: {start, my_events, help, cancel}
  - texts: messages/templates
  - buttons: button labels/templates
- Missing keys fall back to defaults (bot never breaks).
"""

import os
import re
import json
import sqlite3
import logging
import asyncio
import secrets
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    Defaults,
)
from telegram.request import HTTPXRequest

# ----------------------------
# Config
# ----------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_FILE = os.getenv("DB_FILE", "event_companion.db").strip()
STRINGS_FILE = os.getenv("STRINGS_FILE", "strings.json").strip()
APP_TZ = ZoneInfo(os.getenv("APP_TZ", "Europe/Berlin"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("EventCompanionV2")

# ----------------------------
# Dynamic UI (JSON): commands/texts/buttons
# ----------------------------
DEFAULT_UI: Dict[str, Dict[str, str]] = {
    "commands": {
        "start": "start",
        "my_events": "my_events",
        "help": "help",
        "cancel": "cancel",
    },
    "texts": {
        "welcome": "👋 Welcome to <b>EventCompanion</b>!\n\nUse:\n• /{my_events}\n• /{help}\n• /{cancel}",
        "help": (
            "ℹ️ <b>Help</b>\n\n"
            "Commands:\n"
            "• /{my_events} — show your events\n"
            "• /{help} — show this help\n"
            "• /{cancel} — cancel current step\n\n"
            "Tip: After opening an event you’ll see action buttons."
        ),
        "cancelled": "✅ Cancelled.",
        "my_events_title": "📋 <b>My events</b>\nChoose what you want to do:",
        "invalid_event_link": "❌ Invalid event link. Please contact the organizer.",
        "choose_event_first": "Choose an event first: /{my_events}",
        "unknown_action": "⚠️ Unknown action. Use /{my_events} or /start.",
        "events_you_organize": "👑 <b>Events you organize</b>",
        "events_you_joined": "🎟 <b>Events you joined</b>",
        "create_event_prompt": "➕ <b>Create new event</b>\n\nPlease send the <b>event name</b>:",
        "event_not_found": "❌ Event not found.",
        "entered_event": "✅ You’re now in <b>{title}</b>\nRole: <b>{role}</b>\n\nChoose an action:",
        "invite_title": "🔗 <b>Invite</b> — <b>{title}</b>\n\nUse the buttons below:",
        "invite_only_admin": "❌ Only the organizer can view invite here.",
        "delete_confirm": "🗑 <b>Delete this event?</b>\nThis cannot be undone.",
        "event_deleted": "✅ Event deleted.",
        "leave_confirm": "🚪 <b>Leave this event?</b>",
        "left_event": "✅ You left the event.",
        "organizer_cant_leave": "❌ Organizers can't leave their own event.",
        "not_allowed": "❌ Not allowed.",
        "sent_event_info": "✅ Sent event info.",
        "no_photos_yet": "📷 No photos yet.",
        "sent_n_photos": "✅ Sent {n} photo(s).",
        "upload_mode_title": "⬆️ <b>Upload mode</b>\n\nSend photos now (each will be saved).\nTap Done to exit.",
        "upload_mode_closed": "✅ Upload mode closed.",
        "photo_saved_send_more": "✅ Photo saved. Send another, or tap Done.",
        "photo_received_use_photos": "📷 Photo received. Use Photos menu to upload/view.",
        "agenda_updated": "✅ Agenda updated.",
        "wifi_updated": "✅ WiFi updated.",
        "org_updated": "✅ Organizer info updated.",
        "time_updated": "✅ Time updated.",
        "location_updated": "✅ Location updated.",
        "map_pin_saved": "✅ Map pin saved.",
        "map_pin_removed": "✅ Map pin removed.",
        "reg_full_name_prompt": "📝 Registration for this event\n\nPlease enter your <b>Full Name</b>:",
        "reg_phone_prompt": "📞 Please share your <b>Phone number</b> using the button below:",
        "reg_phone_reject": "❌ Please tap the button to share your phone number (Contact).",
        "reg_company_prompt": "🏢 Please enter your <b>Company name</b>:",
        "reg_saved": "✅ Registration saved.",
        "broadcast_sending": "📢 Sending to {n} participants…",
        "broadcast_done": "✅ Done.\nSuccess: {success}\nFailed: {fail}",
        "broadcast_none": "❌ No participants to notify (excluding organizer).",
        "reminder_scheduled": "✅ Reminder scheduled for <b>{when}</b> ({minutes} min before).",
        "reminder_past": "❌ That reminder time is in the past. Please set a future event time.",
        "event_time_not_set": "❌ Event time is not set. Set time first.",
        "ask_question_prompt": "💬 <b>Ask an anonymous question</b> — <b>{title}</b>\n\nType your question now:",
        "question_sent": "✅ Sent! The organizer will receive your question.",
        "rating_choose": "⭐ <b>Feedback</b> — <b>{title}</b>\n\nChoose a rating:",
        "rating_saved_optional_comment": "✅ Rating saved.\n\n(Optional) Send a comment, or tap Skip:",
        "feedback_saved": "✅ Thanks! Your feedback was saved.",
        "comment_empty": "❌ Comment is empty. Send a comment, or tap Skip.",
        "comment_saved": "✅ Thanks! Your comment was saved.",
        "members_none": "No members yet.",
        "questions_none": "💬 No anonymous questions yet.",
        "photos_menu_title": "📷 <b>Photos</b> — <b>{title}</b>",
        "push_prompt": "📢 <b>Push notification</b> — <b>{title}</b>\n\nSend the message to broadcast to participants.\n(You can also send a photo with a caption.)",
        "alert_menu": "⏰ <b>Alert participants</b> — <b>{title}</b>\n\nChoose when to remind participants:",
        "use_my_events_to_continue": "Use /{my_events} to continue.",
        "share_own_contact": "❌ Please share your own contact.",
        "phone_read_fail": "❌ Could not read phone number. Please try again.",
        "map_pin_need_location": "❌ Please send a Telegram Location (📎 → Location), or type <code>clear</code>.",
        "create_event_invalid_name": "❌ Please send a valid event name.",
        "reg_name_invalid": "❌ Please enter a valid Full Name:",
        "reg_company_invalid": "❌ Please enter a valid Company name:",
        "wifi_invalid_format": "❌ Invalid format.\nSend:\nSSID: your_network\nPassword: your_password",
        "wifi_invalid_password": "❌ Invalid password (min 8 characters).",
        "time_invalid_format": "❌ Invalid format. Use: YYYY-MM-DD HH:MM\nExample: 2026-01-15 15:30",
        "location_set_prompt": (
            "📍 <b>Set location</b> — <b>{title}</b>\n\n"
            "Current: <b>{current}</b>\n\n"
            "Send the new location text.\n"
            "Type <code>clear</code> to remove location."
        ),
        "map_pin_set_prompt": (
            "📍 <b>Set map pin</b> — <b>{title}</b>\n\n"
            "Now send a <b>Telegram Location</b> (📎 → Location).\n\n"
            "To remove pin, type <code>clear</code>."
        ),
        "wifi_set_prompt": (
            "📶 <b>Update WiFi</b> — <b>{title}</b>\n\n"
            "Send in 2 lines:\n"
            "<b>SSID:</b> your_network\n"
            "<b>Password:</b> your_password\n\n"
            "Password must be at least <b>8 characters</b>."
        ),
        "org_set_prompt": (
            "👤 <b>Update organizer info</b> — <b>{title}</b>\n\n"
            "Send in format:\n"
            "Name: John Doe\n"
            "Phone: +1234567890\n"
            "Email: john@example.com\n"
            "Telegram: @johndoe"
        ),
        "time_set_prompt": (
            "🕒 <b>Set time</b> — <b>{title}</b>\n\n"
            "Current: <b>{current}</b>\n\n"
            "Send time as:\n<b>YYYY-MM-DD HH:MM</b>\n\nExample:\n2026-01-15 15:30"
        ),
        "agenda_set_prompt": "✏️ <b>Update agenda</b> — <b>{title}</b>\n\nSend the new agenda text:",
        "manage_title": "⚙️ <b>Manage</b> — <b>{title}</b>",
        "view_title": "👀 <b>View</b> — <b>{title}</b>",
        "agenda_title": "📅 <b>Agenda</b> — <b>{title}</b>",
        "wifi_title": "📶 <b>WiFi</b> — <b>{title}</b>",
        "org_title": "👤 <b>Organizer info</b> — <b>{title}</b>",
        "time_title": "🕒 <b>Time</b> — <b>{title}</b>",
        "location_title": "📍 <b>Location</b> — <b>{title}</b>",
        "map_pin_title": "📍 <b>Map pin</b> — <b>{title}</b>\n\nChoose an action:",
        "current_agenda": "📅 <b>Current agenda</b> — <b>{title}</b>\n\n{value}",
        "current_wifi": "📶 <b>Current WiFi</b> — <b>{title}</b>\n\n{value}",
        "current_org": "👤 <b>Current organizer info</b> — <b>{title}</b>\n\n{value}",
        "current_time": "🕒 <b>Current time</b> — <b>{title}</b>\n\n<b>{value}</b>",
        "current_location": "📍 <b>Current location</b> — <b>{title}</b>\n\n<b>{value}</b>",
        "current_map_pin": "📍 <b>Current map pin</b> — <b>{title}</b>\n\n{value}",
        "members_title": "👥 <b>Members</b> — <b>{title}</b>\n\n{value}",
        "questions_title": "💬 <b>Anonymous questions</b> — <b>{title}</b>\n\n{value}",
        "feedback_title": "⭐ <b>Feedback</b> — <b>{title}</b>\n\n{value}",
        "share_invite_title": "🔗 <b>Invite</b> — <b>{title}</b>\n\nUse the buttons below:",
        "push_photo_note": "",
    },
    "buttons": {
        "back": "⬅ Back",
        "cancel": "❌ Cancel",
        "yes": "✅ Yes",
        "no": "❌ No",
        "done": "✅ Done",
        "skip": "⏭ Skip",

        "hub_admin": "👑 Events I organize ({n})",
        "hub_joined": "🎟 Events I joined ({n})",
        "hub_create": "➕ Create new event",

        "event_item_admin": "📌 {name}",
        "event_item_joined": "🎟 {name}",

        "invite": "🔗 Invite",
        "share": "📤 Share",
        "delete_event": "🗑 Delete event",
        "leave_event": "🚪 Leave",

        "manage": "⚙️ Manage",
        "view": "👀 View",
        "push": "📢 Push notification",
        "alert": "⏰ Alert participants",
        "invite_link": "🔗 Invite link",

        "p_info": "ℹ️ Event info",
        "p_share": "📤 Share invite",
        "p_ask": "💬 Ask anonymous question",
        "p_feedback": "⭐ Feedback",
        "p_leave": "🚪 Leave event",

        "agenda": "📅 Agenda",
        "time": "🕒 Time",
        "location": "📍 Location",
        "map_pin": "📍 Map pin",
        "wifi": "📶 WiFi",
        "organizer": "👤 Organizer info",
        "photos": "📷 Photos",

        "view_current": "👁 View current",
        "update_set": "✏️ Update / Set",

        "members": "👥 Members",
        "anon_questions": "💬 Anonymous questions",
        "feedback_summary": "⭐ Feedback summary",

        "photos_view": "📷 View photos",
        "photos_upload": "⬆️ Upload photos",

        "alert_before": "⏰ {m} min before",

        "positive": "👍 Positive",
        "negative": "👎 Negative",
    },
}

_UI: Dict[str, Dict[str, str]] = {}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_ui():
    """Load STRINGS_FILE over DEFAULT_UI, safely."""
    global _UI
    _UI = json.loads(json.dumps(DEFAULT_UI))  # deep copy
    try:
        if os.path.exists(STRINGS_FILE):
            with open(STRINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _UI = _deep_merge(_UI, data)
        logger.info(f"UI loaded from {STRINGS_FILE}")
    except Exception as e:
        logger.warning(f"Failed to load UI file {STRINGS_FILE}: {e}")
        _UI = json.loads(json.dumps(DEFAULT_UI))


def cmd(key: str) -> str:
    return str((_UI.get("commands") or {}).get(key) or (DEFAULT_UI["commands"].get(key) or key))


def btn(key: str, **kwargs) -> str:
    s = (_UI.get("buttons") or {}).get(key) or (DEFAULT_UI.get("buttons") or {}).get(key) or key
    try:
        return str(s).format(**kwargs)
    except Exception:
        return str(s)


def txt(key: str, **kwargs) -> str:
    s = (_UI.get("texts") or {}).get(key) or (DEFAULT_UI.get("texts") or {}).get(key) or key
    base = {
        "start": cmd("start"),
        "my_events": cmd("my_events"),
        "help": cmd("help"),
        "cancel": cmd("cancel"),
    }
    base.update(kwargs)
    try:
        return str(s).format(**base)
    except Exception:
        return str(s)


# ----------------------------
# Helpers
# ----------------------------
def now_ts() -> str:
    return datetime.now(tz=APP_TZ).isoformat(timespec="seconds")


def norm_username(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    return u.lstrip("@").strip().lower() or None


def norm_phone(p: Optional[str]) -> Optional[str]:
    if not p:
        return None
    p = p.strip().replace(" ", "").replace("-", "")
    p = re.sub(r"[^0-9+]", "", p)
    return p or None


def parse_event_time(text: str) -> Optional[datetime]:
    """
    Accepts: YYYY-MM-DD HH:MM
    """
    text = text.strip()
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=APP_TZ)
    except Exception:
        return None


def display_event_time(dt_iso: Optional[str]) -> str:
    if not dt_iso:
        return "Not set"
    try:
        dt = datetime.fromisoformat(dt_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=APP_TZ)
        return dt.astimezone(APP_TZ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_iso


def html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def clamp_caption(text: str, limit: int = 1024) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


async def safe_edit_or_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = ParseMode.HTML,
    disable_web_page_preview: bool = True,
):
    """
    Prefer editing callback messages; fallback to sending.
    NEVER send empty text (Telegram rejects it).
    """
    text = (text or "").strip()
    if not text:
        text = "…"  # safe fallback

    if update.callback_query and update.callback_query.message:
        try:
            await update.callback_query.message.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
            return
        except Exception as e:
            logger.debug(f"edit_text failed, fallback to send: {e}")

    if update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )


# ----------------------------
# Database
# ----------------------------
class Database:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_file, timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            cur = conn.cursor()

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    event_name TEXT,
                    admin_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS event_content (
                    event_id TEXT PRIMARY KEY,
                    agenda TEXT,
                    wifi_ssid TEXT,
                    wifi_password TEXT,
                    organizer_name TEXT,
                    organizer_phone TEXT,
                    organizer_email TEXT,
                    organizer_telegram TEXT,
                    event_time TEXT,
                    event_location TEXT,
                    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
                )
            """
            )

            # ---- Migration: map pin location (lat/lon) ----
            cur.execute("PRAGMA table_info(event_content)")
            cols = {r[1] for r in cur.fetchall()}
            if "loc_lat" not in cols:
                cur.execute("ALTER TABLE event_content ADD COLUMN loc_lat REAL")
            if "loc_lon" not in cols:
                cur.execute("ALTER TABLE event_content ADD COLUMN loc_lon REAL")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    telegram_id INTEGER,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    full_name TEXT,
                    phone_number TEXT,
                    company_name TEXT,
                    registered_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE,
                    UNIQUE(event_id, telegram_id)
                )
            """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    file_id TEXT NOT NULL,
                    caption TEXT,
                    uploaded_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
                )
            """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS anonymous_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    sender_telegram_id INTEGER,
                    question_text TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    status TEXT DEFAULT 'new',
                    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
                )
            """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    telegram_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL,
                    comment TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE,
                    UNIQUE(event_id, telegram_id)
                )
            """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_state (
                    telegram_id INTEGER PRIMARY KEY,
                    state TEXT,
                    payload_json TEXT,
                    updated_at TEXT
                )
            """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_context (
                    telegram_id INTEGER PRIMARY KEY,
                    current_event_id TEXT,
                    updated_at TEXT
                )
            """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    run_at_iso TEXT NOT NULL,
                    minutes_before INTEGER NOT NULL,
                    created_by INTEGER NOT NULL,
                    status TEXT DEFAULT 'scheduled',
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
                )
            """
            )

            cur.execute("CREATE INDEX IF NOT EXISTS idx_events_admin ON events(admin_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_participants_event ON participants(event_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_photos_event ON photos(event_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_questions_event ON anonymous_questions(event_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_event ON feedback(event_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_runat ON alerts(run_at_iso)")

        logger.info("Database initialized")

    # ---- Event methods ----
    def create_event(self, event_id: str, admin_id: int, event_name: str):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO events(event_id, event_name, admin_id, created_at) VALUES(?,?,?,?)",
                (event_id, event_name, admin_id, now_ts()),
            )
            cur.execute("INSERT OR IGNORE INTO event_content(event_id) VALUES(?)", (event_id,))

    def delete_event(self, event_id: str):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM events WHERE event_id=?", (event_id,))

    def event_exists(self, event_id: str) -> bool:
        with self.get_connection() as conn:
            row = conn.execute("SELECT 1 FROM events WHERE event_id=?", (event_id,)).fetchone()
            return bool(row)

    def get_event(self, event_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT event_id, event_name, admin_id, created_at FROM events WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "event_id": row[0],
                "event_name": row[1] or f"Event {row[0][:8]}",
                "admin_id": row[2],
                "created_at": row[3],
            }

    def get_admin_events(self, admin_id: int) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT event_id, event_name, admin_id, created_at FROM events WHERE admin_id=? ORDER BY created_at DESC",
                (admin_id,),
            ).fetchall()
            return [
                {
                    "event_id": r[0],
                    "event_name": r[1] or f"Event {r[0][:8]}",
                    "admin_id": r[2],
                    "created_at": r[3],
                }
                for r in rows
            ]

    def is_admin(self, event_id: str, user_id: int) -> bool:
        with self.get_connection() as conn:
            row = conn.execute("SELECT admin_id FROM events WHERE event_id=?", (event_id,)).fetchone()
            return bool(row) and row[0] == user_id

    def get_participating_events(self, telegram_id: int) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT e.event_id, e.event_name, e.admin_id, e.created_at
                FROM participants p
                JOIN events e ON e.event_id = p.event_id
                WHERE p.telegram_id = ?
                ORDER BY e.created_at DESC
                """,
                (telegram_id,),
            ).fetchall()
            return [
                {
                    "event_id": r[0],
                    "event_name": r[1] or f"Event {r[0][:8]}",
                    "admin_id": r[2],
                    "created_at": r[3],
                }
                for r in rows
            ]

    # ---- Event content ----
    def get_event_content(self, event_id: str) -> Dict:
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT agenda, wifi_ssid, wifi_password,
                       organizer_name, organizer_phone, organizer_email, organizer_telegram,
                       event_time, event_location,
                       loc_lat, loc_lon
                FROM event_content WHERE event_id=?
                """,
                (event_id,),
            ).fetchone()
            if not row:
                return {}
            return {
                "agenda": row[0],
                "wifi_ssid": row[1],
                "wifi_password": row[2],
                "organizer_name": row[3],
                "organizer_phone": row[4],
                "organizer_email": row[5],
                "organizer_telegram": row[6],
                "event_time": row[7],
                "event_location": row[8],
                "loc_lat": row[9],
                "loc_lon": row[10],
            }

    def set_agenda(self, event_id: str, agenda: str):
        with self.get_connection() as conn:
            conn.execute("UPDATE event_content SET agenda=? WHERE event_id=?", (agenda, event_id))

    def set_wifi(self, event_id: str, ssid: str, password: str):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE event_content SET wifi_ssid=?, wifi_password=? WHERE event_id=?",
                (ssid, password, event_id),
            )

    def set_organizer_info(self, event_id: str, name: str, phone: str, email: str, tg: str):
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE event_content
                SET organizer_name=?, organizer_phone=?, organizer_email=?, organizer_telegram=?
                WHERE event_id=?
                """,
                (name, phone, email, tg, event_id),
            )

    def set_time(self, event_id: str, event_time_iso: Optional[str]):
        with self.get_connection() as conn:
            conn.execute("UPDATE event_content SET event_time=? WHERE event_id=?", (event_time_iso, event_id))

    def set_location(self, event_id: str, location: Optional[str]):
        with self.get_connection() as conn:
            conn.execute("UPDATE event_content SET event_location=? WHERE event_id=?", (location, event_id))

    def set_map_pin(self, event_id: str, lat: float, lon: float):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE event_content SET loc_lat=?, loc_lon=? WHERE event_id=?",
                (lat, lon, event_id),
            )

    def clear_map_pin(self, event_id: str):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE event_content SET loc_lat=NULL, loc_lon=NULL WHERE event_id=?",
                (event_id,),
            )

    # ---- Participants ----
    def ensure_participant_stub(
        self,
        event_id: str,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
    ):
        username = norm_username(username)
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO participants(event_id, telegram_id, username, first_name, last_name, registered_at)
                VALUES(?,?,?,?,?,?)
                """,
                (event_id, telegram_id, username, first_name, last_name, now_ts()),
            )
            conn.execute(
                """
                UPDATE participants
                SET username=COALESCE(?, username),
                    first_name=COALESCE(?, first_name),
                    last_name=COALESCE(?, last_name)
                WHERE event_id=? AND telegram_id=?
                """,
                (username, first_name, last_name, event_id, telegram_id),
            )

    def has_full_registration(self, event_id: str, telegram_id: int) -> bool:
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT full_name, phone_number, company_name
                FROM participants WHERE event_id=? AND telegram_id=?
                """,
                (event_id, telegram_id),
            ).fetchone()
            if not row:
                return False
            full_name, phone, company = row
            return bool((full_name or "").strip()) and bool((phone or "").strip()) and bool((company or "").strip())

    def set_registration_info(self, event_id: str, telegram_id: int, full_name: str, phone: str, company: str):
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE participants
                SET full_name=?, phone_number=?, company_name=?
                WHERE event_id=? AND telegram_id=?
                """,
                (full_name.strip(), norm_phone(phone), company.strip(), event_id, telegram_id),
            )

    def list_members(self, event_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT telegram_id, username, first_name, last_name, full_name, phone_number, company_name, registered_at
                FROM participants
                WHERE event_id=?
                ORDER BY registered_at DESC
                """,
                (event_id,),
            ).fetchall()
            out = []
            for r in rows:
                out.append(
                    {
                        "telegram_id": r[0],
                        "username": r[1],
                        "first_name": r[2],
                        "last_name": r[3],
                        "full_name": r[4],
                        "phone_number": r[5],
                        "company_name": r[6],
                        "registered_at": r[7],
                    }
                )
            return out

    def leave_event(self, event_id: str, telegram_id: int):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM participants WHERE event_id=? AND telegram_id=?", (event_id, telegram_id))

    def get_participant_telegram_ids(self, event_id: str) -> List[int]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT telegram_id FROM participants WHERE event_id=? AND telegram_id IS NOT NULL",
                (event_id,),
            ).fetchall()
            return [r[0] for r in rows if r and r[0] is not None]

    # ---- Photos ----
    def add_photo(self, event_id: str, file_id: str, caption: Optional[str]):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO photos(event_id, file_id, caption, uploaded_at) VALUES(?,?,?,?)",
                (event_id, file_id, caption, now_ts()),
            )

    def get_photos(self, event_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT file_id, caption FROM photos WHERE event_id=? ORDER BY uploaded_at ASC",
                (event_id,),
            ).fetchall()
            return [{"file_id": r[0], "caption": r[1]} for r in rows]

    # ---- Anonymous questions ----
    def add_question(self, event_id: str, sender_id: int, text: str):
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO anonymous_questions(event_id, sender_telegram_id, question_text, created_at, status)
                VALUES(?,?,?,?, 'new')
                """,
                (event_id, sender_id, text, now_ts()),
            )

    def list_questions(self, event_id: str, limit: int = 50) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, question_text, created_at, status
                FROM anonymous_questions
                WHERE event_id=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (event_id, limit),
            ).fetchall()
            return [{"id": r[0], "text": r[1], "created_at": r[2], "status": r[3]} for r in rows]

    # ---- Feedback ----
    def set_feedback(self, event_id: str, telegram_id: int, rating: int, comment: Optional[str] = None):
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO feedback(event_id, telegram_id, rating, comment, created_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(event_id, telegram_id) DO UPDATE SET
                    rating=excluded.rating,
                    comment=COALESCE(excluded.comment, feedback.comment),
                    created_at=excluded.created_at
                """,
                (event_id, telegram_id, rating, comment, now_ts()),
            )

    def get_feedback_summary(self, event_id: str) -> Dict:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT rating, COUNT(*) FROM feedback WHERE event_id=? GROUP BY rating",
                (event_id,),
            ).fetchall()
            up = 0
            down = 0
            for r, c in rows:
                if r == 1:
                    up = c
                elif r == -1:
                    down = c
            total = up + down
            return {"up": up, "down": down, "total": total}

    def list_feedback_comments(self, event_id: str, limit: int = 50) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT telegram_id, rating, comment, created_at
                FROM feedback
                WHERE event_id=? AND comment IS NOT NULL AND TRIM(comment) != ''
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (event_id, limit),
            ).fetchall()
            return [{"telegram_id": r[0], "rating": r[1], "comment": r[2], "created_at": r[3]} for r in rows]

    # ---- State persistence ----
    def set_user_state(self, telegram_id: int, state: Optional[str], payload: Optional[Dict] = None):
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        with self.get_connection() as conn:
            if state is None:
                conn.execute("DELETE FROM user_state WHERE telegram_id=?", (telegram_id,))
            else:
                conn.execute(
                    """
                    INSERT INTO user_state(telegram_id, state, payload_json, updated_at)
                    VALUES(?,?,?,?)
                    ON CONFLICT(telegram_id) DO UPDATE SET
                        state=excluded.state,
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                    """,
                    (telegram_id, state, payload_json, now_ts()),
                )

    def get_user_state(self, telegram_id: int) -> Tuple[Optional[str], Dict]:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT state, payload_json FROM user_state WHERE telegram_id=?",
                (telegram_id,),
            ).fetchone()
            if not row:
                return None, {}
            st = row[0]
            try:
                payload = json.loads(row[1] or "{}")
            except Exception:
                payload = {}
            return st, payload

    def clear_user_state(self, telegram_id: int):
        self.set_user_state(telegram_id, None, None)

    def set_current_event(self, telegram_id: int, event_id: Optional[str]):
        with self.get_connection() as conn:
            if event_id is None:
                conn.execute("DELETE FROM user_context WHERE telegram_id=?", (telegram_id,))
            else:
                conn.execute(
                    """
                    INSERT INTO user_context(telegram_id, current_event_id, updated_at)
                    VALUES(?,?,?)
                    ON CONFLICT(telegram_id) DO UPDATE SET
                        current_event_id=excluded.current_event_id,
                        updated_at=excluded.updated_at
                    """,
                    (telegram_id, event_id, now_ts()),
                )

    def get_current_event(self, telegram_id: int) -> Optional[str]:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT current_event_id FROM user_context WHERE telegram_id=?",
                (telegram_id,),
            ).fetchone()
            return row[0] if row and row[0] else None

    # ---- Alerts ----
    def add_alert(self, event_id: str, run_at_iso: str, minutes_before: int, created_by: int) -> int:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO alerts(event_id, run_at_iso, minutes_before, created_by, status)
                VALUES(?,?,?,?, 'scheduled')
                """,
                (event_id, run_at_iso, minutes_before, created_by),
            )
            return cur.lastrowid

    def list_future_alerts(self) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, event_id, run_at_iso, minutes_before, created_by, status
                FROM alerts
                WHERE status='scheduled'
                """,
            ).fetchall()
            out = []
            for r in rows:
                out.append(
                    {
                        "id": r[0],
                        "event_id": r[1],
                        "run_at_iso": r[2],
                        "minutes_before": r[3],
                        "created_by": r[4],
                        "status": r[5],
                    }
                )
            return out

    def mark_alert_sent(self, alert_id: int):
        with self.get_connection() as conn:
            conn.execute("UPDATE alerts SET status='sent' WHERE id=?", (alert_id,))


db = Database(DB_FILE)

# ----------------------------
# Inline UI builders
# ----------------------------
def kb_cancel(back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(btn("cancel"), callback_data=back_cb)]])


def kb_hub(user_id: int) -> InlineKeyboardMarkup:
    admin_events = db.get_admin_events(user_id)
    joined = db.get_participating_events(user_id)
    rows = [
        [InlineKeyboardButton(btn("hub_admin", n=len(admin_events)), callback_data="hub:admin")],
        [InlineKeyboardButton(btn("hub_joined", n=len(joined)), callback_data="hub:joined")],
        [InlineKeyboardButton(btn("hub_create"), callback_data="event:create")],
    ]
    return InlineKeyboardMarkup(rows)


def kb_hub_list_admin(user_id: int, bot_username: str) -> InlineKeyboardMarkup:
    events = db.get_admin_events(user_id)
    rows: List[List[InlineKeyboardButton]] = []

    if not events:
        rows.append([InlineKeyboardButton(btn("hub_create"), callback_data="event:create")])
        rows.append([InlineKeyboardButton(btn("back"), callback_data="hub:none")])
        return InlineKeyboardMarkup(rows)

    for e in events:
        eid = e["event_id"]
        name = e["event_name"]
        rows.append(
            [InlineKeyboardButton(btn("event_item_admin", name=name), callback_data=f"event:open:{eid}:hub_admin")]
        )

    # Back at bottom
    rows.append([InlineKeyboardButton(btn("back"), callback_data="hub:none")])
    return InlineKeyboardMarkup(rows)




def kb_hub_list_joined(user_id: int, bot_username: str) -> InlineKeyboardMarkup:
    events = db.get_participating_events(user_id)
    rows: List[List[InlineKeyboardButton]] = []

    if not events:
        rows.append([InlineKeyboardButton(btn("back"), callback_data="hub:none")])
        return InlineKeyboardMarkup(rows)

    for e in events:
        eid = e["event_id"]
        name = e["event_name"]
        rows.append(
            [InlineKeyboardButton(btn("event_item_joined", name=name), callback_data=f"event:open:{eid}:hub_joined")]
        )

    # Back at bottom
    rows.append([InlineKeyboardButton(btn("back"), callback_data="hub:none")])
    return InlineKeyboardMarkup(rows)




def kb_confirm(action_yes: str, action_no: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(btn("yes"), callback_data=action_yes), InlineKeyboardButton(btn("no"), callback_data=action_no)]]
    )


def kb_admin_manage(event_id: str, user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(btn("agenda"), callback_data="admin:agenda"),
            InlineKeyboardButton(btn("time"), callback_data="admin:time"),
        ],
        [
            InlineKeyboardButton(btn("location"), callback_data="admin:location"),
            InlineKeyboardButton(btn("map_pin"), callback_data="admin:map_pin"),
        ],
        [
            InlineKeyboardButton(btn("wifi"), callback_data="admin:wifi"),
            InlineKeyboardButton(btn("organizer"), callback_data="admin:org"),
        ],
        [InlineKeyboardButton(btn("photos"), callback_data="admin:photos")],
        [InlineKeyboardButton(btn("back"), callback_data="admin:back_to_menu")],
    ]
    return InlineKeyboardMarkup(rows)



def kb_admin_view(event_id: str, user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(btn("members"), callback_data="admin:members")],
        [InlineKeyboardButton(btn("anon_questions"), callback_data="admin:questions")],
        [InlineKeyboardButton(btn("feedback_summary"), callback_data="admin:feedback")],
        [InlineKeyboardButton(btn("back"), callback_data="admin:back_to_menu")],
    ]
    return InlineKeyboardMarkup(rows)


def kb_event_menu(event_id: str, user_id: int, src: str, share_url: Optional[str] = None) -> InlineKeyboardMarkup:
    is_admin = db.is_admin(event_id, user_id)
    rows: List[List[InlineKeyboardButton]] = []

    if is_admin:
        rows += [
            [InlineKeyboardButton(btn("manage"), callback_data="admin:manage"),
             InlineKeyboardButton(btn("view"), callback_data="admin:view")],
            [InlineKeyboardButton(btn("push"), callback_data="admin:notify"),
             InlineKeyboardButton(btn("alert"), callback_data="admin:alert")],
        ]

        # ✅ one-tap share (no intermediate screen)
        if share_url:
            rows.append([InlineKeyboardButton(btn("share"), url=share_url)])
        else:
            # fallback (should rarely happen)
            rows.append([InlineKeyboardButton(btn("invite_link"), callback_data="admin:invite")])

        rows.append([InlineKeyboardButton(btn("delete_event"), callback_data="admin:delete")])

    else:
        rows += [
            [InlineKeyboardButton(btn("p_info"), callback_data="p:info"),
             InlineKeyboardButton(btn("p_share"), url=share_url) if share_url else InlineKeyboardButton(btn("p_share"), callback_data="p:share")],
            [InlineKeyboardButton(btn("p_ask"), callback_data="p:ask"),
             InlineKeyboardButton(btn("p_feedback"), callback_data="p:feedback")],
            [InlineKeyboardButton(btn("p_leave"), callback_data="p:leave")],
        ]

    if src == "hub_admin":
        back_cb = "hub:admin"
    elif src == "hub_joined":
        back_cb = "hub:joined"
    else:
        back_cb = "hub:none"

    rows.append([InlineKeyboardButton(btn("back"), callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)



def kb_admin_field_menu(field: str, back: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(btn("view_current"), callback_data=f"admin:{field}_view")],
            [InlineKeyboardButton(btn("update_set"), callback_data=f"admin:{field}_edit")],
            [InlineKeyboardButton(btn("back"), callback_data=back)],
        ]
    )


# ----------------------------
# Bot username & invite link
# ----------------------------
async def ensure_bot_username(context: ContextTypes.DEFAULT_TYPE):
    if "bot_username" in context.application.bot_data:
        return
    me = await context.bot.get_me()
    context.application.bot_data["bot_username"] = me.username


def get_bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.application.bot_data.get("bot_username") or (context.bot.username or "")


def invite_link_for(context: ContextTypes.DEFAULT_TYPE, event_id: str) -> str:
    bot_username = get_bot_username(context)
    return f"https://t.me/{bot_username}?start={event_id}"


# ----------------------------
# Current event context
# ----------------------------
def get_current_event_id(user_id: int) -> Optional[str]:
    return db.get_current_event(user_id)


def set_current_event_id(user_id: int, event_id: Optional[str]):
    db.set_current_event(user_id, event_id)


# ----------------------------
# Rendering event info (participant)
# ----------------------------
def build_event_info_text(event_id: str) -> str:
    ev = db.get_event(event_id)
    content = db.get_event_content(event_id)
    if not ev:
        return txt("event_not_found")

    title = html_escape(ev["event_name"])
    tm = html_escape(display_event_time(content.get("event_time")))
    loc = html_escape(content.get("event_location") or "Not set")

    lat = content.get("loc_lat")
    lon = content.get("loc_lon")
    map_line = "Not set"
    if lat is not None and lon is not None:
        map_line = f"<a href=\"https://maps.google.com/?q={lat},{lon}\">Open map pin</a>"

    agenda = content.get("agenda") or ""
    agenda_disp = html_escape(agenda) if agenda.strip() else "Not available yet."

    org = (
        f"Name: <b>{html_escape(content.get('organizer_name') or 'N/A')}</b>\n"
        f"Phone: <b>{html_escape(content.get('organizer_phone') or 'N/A')}</b>\n"
        f"Email: <b>{html_escape(content.get('organizer_email') or 'N/A')}</b>\n"
        f"Telegram: <b>{html_escape(content.get('organizer_telegram') or 'N/A')}</b>\n"
    )

    ssid = content.get("wifi_ssid")
    pwd = content.get("wifi_password")
    wifi = "Not available yet."
    if ssid and pwd:
        wifi = f"SSID: <b>{html_escape(ssid)}</b>\nPassword: <b>{html_escape(pwd)}</b>"

    txt_out = (
        f"ℹ️ <b>{title}</b>\n\n"
        f"🕒 Time: <b>{tm}</b>\n"
        f"📍 Location: <b>{loc}</b>\n"
        f"🗺 Map: {map_line}\n\n"
        f"📅 <b>Agenda</b>\n{agenda_disp}\n\n"
        f"👤 <b>Organizer</b>\n{org}\n"
        f"📶 <b>WiFi</b>\n{wifi}\n"
    )
    return txt_out


async def send_event_info_with_photos(update: Update, context: ContextTypes.DEFAULT_TYPE, event_id: str):
    chat_id = update.effective_chat.id
    photos = db.get_photos(event_id)
    info = build_event_info_text(event_id)
    caption = clamp_caption(info)

    if not photos:
        await safe_edit_or_send(
            update,
            context,
            caption,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn("back"), callback_data="p:back_to_menu")]]),
            parse_mode=ParseMode.HTML,
        )
        return

    first = True
    for i in range(0, len(photos), 10):
        group = photos[i : i + 10]
        media = []
        for idx, p in enumerate(group):
            if first and idx == 0:
                media.append(InputMediaPhoto(media=p["file_id"], caption=caption, parse_mode=ParseMode.HTML))
            else:
                media.append(InputMediaPhoto(media=p["file_id"]))
        await context.bot.send_media_group(chat_id=chat_id, media=media)
        first = False

    await safe_edit_or_send(
        update,
        context,
        txt("sent_event_info"),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn("back"), callback_data="p:back_to_menu")]]),
        parse_mode=ParseMode.HTML,
    )


# ----------------------------
# Entry points (commands)
# ----------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_bot_username(context)
    load_ui()  # hot reload on /start

    user = update.effective_user
    if not user or not update.message:
        return
    user_id = user.id

    if context.args:
        event_id = context.args[0].strip()
        if not db.event_exists(event_id):
            await update.message.reply_text(txt("invalid_event_link"), parse_mode=ParseMode.HTML)
            return

        db.ensure_participant_stub(event_id, user_id, user.username, user.first_name, user.last_name)
        set_current_event_id(user_id, event_id)

        if (not db.is_admin(event_id, user_id)) and (not db.has_full_registration(event_id, user_id)):
            db.set_user_state(user_id, "reg_full_name", {"event_id": event_id, "src": "hub_joined"})
            await update.message.reply_text(
                txt("reg_full_name_prompt"),
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        await show_event_menu(update, context, event_id=event_id, src="hub_joined")
        return

    db.clear_user_state(user_id)
    await update.message.reply_text(txt("welcome"), parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())


async def cmd_my_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_bot_username(context)
    user = update.effective_user
    if not user or not update.message:
        return
    db.clear_user_state(user.id)

    await update.message.reply_text(
        txt("my_events_title"),
        parse_mode=ParseMode.HTML,
        reply_markup=kb_hub(user.id),
        disable_web_page_preview=True,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    load_ui()
    if not update.message:
        return
    await update.message.reply_text(txt("help"), parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    db.clear_user_state(user.id)
    await update.message.reply_text(txt("cancelled"), parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())


# ----------------------------
# Menus
# ----------------------------
async def show_event_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, event_id: str, src: str):
    user = update.effective_user
    if not user:
        return
    event = db.get_event(event_id)
    if not event:
        await safe_edit_or_send(update, context, txt("event_not_found"))
        return

    set_current_event_id(user.id, event_id)

    is_admin = db.is_admin(event_id, user.id)
    role = "Organizer" if is_admin else "Participant"
    title = html_escape(event["event_name"])

    link = invite_link_for(context, event_id)
    share_url = "https://t.me/share/url?" + urllib.parse.urlencode({"url": link, "text": ""})

    await safe_edit_or_send(
        update,
        context,
        txt("entered_event", title=title, role=role),
        reply_markup=kb_event_menu(event_id, user.id, src, share_url=share_url),
        parse_mode=ParseMode.HTML,
    )


# ----------------------------
# Callback router
# ----------------------------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_bot_username(context)
    q = update.callback_query
    if not q:
        return
    await q.answer()
    user = q.from_user
    user_id = user.id
    data = q.data or ""
    bot_username = get_bot_username(context)

    if data == "hub:none":
        await safe_edit_or_send(update, context, txt("my_events_title"), reply_markup=kb_hub(user_id))
        return

    if data == "hub:admin":
        db.clear_user_state(user_id)
        await safe_edit_or_send(update, context, txt("events_you_organize"), reply_markup=kb_hub_list_admin(user_id, bot_username))
        return

    if data == "hub:joined":
        db.clear_user_state(user_id)
        await safe_edit_or_send(update, context, txt("events_you_joined"), reply_markup=kb_hub_list_joined(user_id, bot_username))
        return

    if data == "event:create":
        db.set_user_state(user_id, "create_event_name", {"src": "hub:none"})
        await safe_edit_or_send(update, context, txt("create_event_prompt"))
        return

    if data.startswith("event:open:"):
        parts = data.split(":")
        if len(parts) < 4:
            return
        event_id = parts[2]
        src = parts[3]
        if not db.event_exists(event_id):
            await safe_edit_or_send(update, context, txt("event_not_found"))
            return

        db.ensure_participant_stub(event_id, user_id, user.username, user.first_name, user.last_name)
        set_current_event_id(user_id, event_id)

        if (not db.is_admin(event_id, user_id)) and (not db.has_full_registration(event_id, user_id)):
            db.set_user_state(user_id, "reg_full_name", {"event_id": event_id, "src": src})
            await safe_edit_or_send(update, context, txt("reg_full_name_prompt"))
            return

        await show_event_menu(update, context, event_id, src)
        return

    if data.startswith("event:invite:"):
        _, _, eid, back = data.split(":")
        if not db.is_admin(eid, user_id):
            await safe_edit_or_send(update, context, "❌ Only the organizer can view invite here.")
            return
        ev = db.get_event(eid)
        title = html_escape(ev["event_name"]) if ev else html_escape(eid)
        link = invite_link_for(context, eid)
        share = "https://t.me/share/url?" + urllib.parse.urlencode({"url": link, "text": ""})

        rows = [
            [InlineKeyboardButton("📤 Share", url=share)],
            [InlineKeyboardButton(btn("back"), callback_data="hub:admin")],
        ]
        await safe_edit_or_send(update, context, txt("invite_title", title=title), reply_markup=InlineKeyboardMarkup(rows))
        return


    if data.startswith("event:del_confirm:"):
        _, _, eid, back = data.split(":")
        if not db.is_admin(eid, user_id):
            await safe_edit_or_send(update, context, txt("not_allowed"))
            return
        await safe_edit_or_send(update, context, txt("delete_confirm"), reply_markup=kb_confirm(f"event:delete:{eid}:{back}", "hub:admin"))
        return

    if data.startswith("event:delete:"):
        _, _, eid, back = data.split(":")
        if not db.is_admin(eid, user_id):
            await safe_edit_or_send(update, context, txt("not_allowed"))
            return
        db.delete_event(eid)
        if db.get_current_event(user_id) == eid:
            set_current_event_id(user_id, None)
        await safe_edit_or_send(update, context, txt("event_deleted"), reply_markup=kb_hub(user_id))
        return

    if data.startswith("event:leave_confirm:"):
        _, _, eid, back = data.split(":")
        if db.is_admin(eid, user_id):
            await safe_edit_or_send(update, context, txt("organizer_cant_leave"))
            return
        await safe_edit_or_send(update, context, txt("leave_confirm"), reply_markup=kb_confirm(f"event:leave:{eid}:{back}", "hub:joined"))
        return

    if data.startswith("event:leave:"):
        _, _, eid, back = data.split(":")
        if db.is_admin(eid, user_id):
            await safe_edit_or_send(update, context, txt("organizer_cant_leave"))
            return
        db.leave_event(eid, user_id)
        if db.get_current_event(user_id) == eid:
            set_current_event_id(user_id, None)
        await safe_edit_or_send(update, context, txt("left_event"), reply_markup=kb_hub(user_id))
        return

    current_event_id = db.get_current_event(user_id)
    if not current_event_id or not db.event_exists(current_event_id):
        await safe_edit_or_send(update, context, txt("choose_event_first"))
        return

    is_admin = db.is_admin(current_event_id, user_id)

    if is_admin and data.startswith("admin:"):
        await handle_admin_action(update, context, current_event_id, data)
        return

    if (not is_admin) and data.startswith("p:"):
        await handle_participant_action(update, context, current_event_id, data)
        return

    await safe_edit_or_send(update, context, txt("unknown_action"))


# ----------------------------
# Admin actions
# ----------------------------
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE, event_id: str, data: str):
    user = update.effective_user
    user_id = user.id
    event = db.get_event(event_id)
    content = db.get_event_content(event_id)
    title = html_escape(event["event_name"])

    if data == "admin:manage":
        await safe_edit_or_send(update, context, txt("manage_title", title=title), reply_markup=kb_admin_manage(event_id, user_id))
        return
    if data == "admin:view":
        await safe_edit_or_send(update, context, txt("view_title", title=title), reply_markup=kb_admin_view(event_id, user_id))
        return

    if data == "admin:agenda":
        await safe_edit_or_send(update, context, txt("agenda_title", title=title), reply_markup=kb_admin_field_menu("agenda", "admin:manage"))
        return
    if data == "admin:wifi":
        await safe_edit_or_send(update, context, txt("wifi_title", title=title), reply_markup=kb_admin_field_menu("wifi", "admin:manage"))
        return
    if data == "admin:org":
        await safe_edit_or_send(update, context, txt("org_title", title=title), reply_markup=kb_admin_field_menu("org", "admin:manage"))
        return
    if data == "admin:time":
        await safe_edit_or_send(update, context, txt("time_title", title=title), reply_markup=kb_admin_field_menu("time", "admin:manage"))
        return
    if data == "admin:location":
        await safe_edit_or_send(update, context, txt("location_title", title=title), reply_markup=kb_admin_field_menu("location", "admin:manage"))
        return

    if data == "admin:map_pin":
        await safe_edit_or_send(
            update,
            context,
            txt("map_pin_title", title=title),
            reply_markup=kb_admin_field_menu("map_pin", "admin:manage"),
        )
        return

    if data == "admin:agenda_view":
        agenda = content.get("agenda") or ""
        value = html_escape(agenda) if agenda.strip() else "Not set"
        await safe_edit_or_send(update, context, txt("current_agenda", title=title, value=value), reply_markup=kb_admin_field_menu("agenda", "admin:manage"))
        return

    if data == "admin:wifi_view":
        ssid = content.get("wifi_ssid")
        pwd = content.get("wifi_password")
        value = f"SSID: <b>{html_escape(ssid)}</b>\nPassword: <b>{html_escape(pwd)}</b>" if (ssid and pwd) else "Not set"
        await safe_edit_or_send(update, context, txt("current_wifi", title=title, value=value), reply_markup=kb_admin_field_menu("wifi", "admin:manage"))
        return

    if data == "admin:org_view":
        value = (
            f"Name: <b>{html_escape(content.get('organizer_name') or 'N/A')}</b>\n"
            f"Phone: <b>{html_escape(content.get('organizer_phone') or 'N/A')}</b>\n"
            f"Email: <b>{html_escape(content.get('organizer_email') or 'N/A')}</b>\n"
            f"Telegram: <b>{html_escape(content.get('organizer_telegram') or 'N/A')}</b>\n"
        )
        await safe_edit_or_send(update, context, txt("current_org", title=title, value=value), reply_markup=kb_admin_field_menu("org", "admin:manage"))
        return

    if data == "admin:time_view":
        current = display_event_time(content.get("event_time"))
        await safe_edit_or_send(update, context, txt("current_time", title=title, value=html_escape(current)), reply_markup=kb_admin_field_menu("time", "admin:manage"))
        return

    if data == "admin:location_view":
        loc = content.get("event_location") or "Not set"
        await safe_edit_or_send(update, context, txt("current_location", title=title, value=html_escape(loc)), reply_markup=kb_admin_field_menu("location", "admin:manage"))
        return

    if data == "admin:map_pin_view":
        lat = content.get("loc_lat")
        lon = content.get("loc_lon")
        if lat is None or lon is None:
            value = "Not set"
        else:
            value = (
                f"<b>Saved:</b> <code>{lat:.6f}, {lon:.6f}</code>\n"
                f"<a href=\"https://maps.google.com/?q={lat},{lon}\">Open in Google Maps</a>"
            )
        await safe_edit_or_send(update, context, txt("current_map_pin", title=title, value=value), reply_markup=kb_admin_field_menu("map_pin", "admin:manage"))
        return

    if data == "admin:agenda_edit":
        db.set_user_state(user_id, "admin_edit_agenda", {"event_id": event_id})
        await safe_edit_or_send(update, context, txt("agenda_set_prompt", title=title), reply_markup=kb_cancel("admin:agenda"))
        return

    if data == "admin:wifi_edit":
        db.set_user_state(user_id, "admin_set_wifi", {"event_id": event_id})
        await safe_edit_or_send(update, context, txt("wifi_set_prompt", title=title), reply_markup=kb_cancel("admin:wifi"))
        return

    if data == "admin:org_edit":
        db.set_user_state(user_id, "admin_set_org", {"event_id": event_id})
        await safe_edit_or_send(update, context, txt("org_set_prompt", title=title), reply_markup=kb_cancel("admin:org"))
        return

    if data == "admin:time_edit":
        db.set_user_state(user_id, "admin_set_time", {"event_id": event_id})
        cur = display_event_time(content.get("event_time"))
        await safe_edit_or_send(update, context, txt("time_set_prompt", title=title, current=html_escape(cur)), reply_markup=kb_cancel("admin:time"))
        return

    if data == "admin:location_edit":
        db.set_user_state(user_id, "admin_set_location", {"event_id": event_id})
        loc = content.get("event_location") or "Not set"
        await safe_edit_or_send(
            update,
            context,
            txt("location_set_prompt", title=title, current=html_escape(loc)),
            reply_markup=kb_cancel("admin:location"),
        )
        return

    if data == "admin:map_pin_edit":
        db.set_user_state(user_id, "admin_set_map_pin", {"event_id": event_id})
        await safe_edit_or_send(update, context, txt("map_pin_set_prompt", title=title), reply_markup=kb_cancel("admin:map_pin"))
        return

    if data == "admin:members":
        members = db.list_members(event_id)
        if not members:
            await safe_edit_or_send(update, context, txt("members_title", title=title, value=txt("members_none")), reply_markup=kb_admin_view(event_id, user_id))
            return

        lines = []
        for i, m in enumerate(members[:60], 1):
            name = (m.get("full_name") or "").strip()
            if not name:
                name = " ".join([x for x in [m.get("first_name"), m.get("last_name")] if x]).strip()
            uname = m.get("username")
            phone = m.get("phone_number")
            company = m.get("company_name")
            ident = []
            if uname:
                ident.append(f"@{html_escape(uname)}")
            if name:
                ident.append(html_escape(name))
            if company:
                ident.append(html_escape(company))
            if phone:
                ident.append(html_escape(phone))
            if not ident:
                ident.append(f"ID:{m.get('telegram_id')}")
            lines.append(f"{i}. " + " • ".join(ident))

        await safe_edit_or_send(update, context, txt("members_title", title=title, value="\n".join(lines)), reply_markup=kb_admin_view(event_id, user_id))
        return

    if data == "admin:notify":
        db.set_user_state(user_id, "admin_notify_text", {"event_id": event_id})
        await safe_edit_or_send(update, context, txt("push_prompt", title=title), reply_markup=kb_cancel("admin:back_to_menu"))
        return

    if data == "admin:alert":
        rows = [
            [
                InlineKeyboardButton(btn("alert_before", m=15), callback_data="admin:alert_set:15"),
                InlineKeyboardButton(btn("alert_before", m=30), callback_data="admin:alert_set:30"),
            ],
            [InlineKeyboardButton(btn("alert_before", m=60), callback_data="admin:alert_set:60")],
            [InlineKeyboardButton(btn("back"), callback_data="admin:back_to_menu")],
        ]
        await safe_edit_or_send(update, context, txt("alert_menu", title=title), reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("admin:alert_set:"):
        minutes = int(data.split(":")[-1])
        et = content.get("event_time")
        dt = datetime.fromisoformat(et) if et else None
        if not dt:
            await safe_edit_or_send(update, context, txt("event_time_not_set"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn("back"), callback_data="admin:alert")]]))
            return
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=APP_TZ)
        run_at = dt - timedelta(minutes=minutes)
        if run_at <= datetime.now(tz=APP_TZ):
            await safe_edit_or_send(update, context, txt("reminder_past"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn("back"), callback_data="admin:alert")]]))
            return

        alert_id = db.add_alert(event_id, run_at.isoformat(timespec="seconds"), minutes, user_id)
        schedule_alert_job(context.application, alert_id, event_id, run_at)

        await safe_edit_or_send(
            update,
            context,
            txt("reminder_scheduled", when=run_at.strftime("%Y-%m-%d %H:%M"), minutes=minutes),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn("back"), callback_data="admin:back_to_menu")]]),
        )
        return

    if data == "admin:photos":
        rows = [
            [InlineKeyboardButton(btn("photos_view"), callback_data="admin:photos_view")],
            [InlineKeyboardButton(btn("photos_upload"), callback_data="admin:photos_upload")],
            [InlineKeyboardButton(btn("back"), callback_data="admin:manage")],
        ]
        await safe_edit_or_send(update, context, txt("photos_menu_title", title=title), reply_markup=InlineKeyboardMarkup(rows))
        return

    if data == "admin:photos_view":
        photos = db.get_photos(event_id)
        if not photos:
            await safe_edit_or_send(update, context, txt("no_photos_yet"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn("back"), callback_data="admin:photos")]]))
            return

        chat_id = update.effective_chat.id
        for i in range(0, len(photos), 10):
            group = photos[i : i + 10]
            if len(group) == 1:
                await context.bot.send_photo(chat_id=chat_id, photo=group[0]["file_id"], caption=group[0]["caption"] or "")
            else:
                media = []
                for idx, p in enumerate(group):
                    media.append(InputMediaPhoto(media=p["file_id"], caption=(p["caption"] if idx == 0 else None)))
                await context.bot.send_media_group(chat_id=chat_id, media=media)

        await safe_edit_or_send(update, context, txt("sent_n_photos", n=len(photos)), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn("back"), callback_data="admin:photos")]]))
        return

    if data == "admin:photos_upload":
        db.set_user_state(user_id, "admin_upload_photos", {"event_id": event_id})
        await safe_edit_or_send(
            update,
            context,
            txt("upload_mode_title"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn("done"), callback_data="admin:photos_done")]]),
        )
        return

    if data == "admin:photos_done":
        db.clear_user_state(user_id)
        await safe_edit_or_send(update, context, txt("upload_mode_closed"), reply_markup=kb_admin_manage(event_id, user_id))
        return

    if data == "admin:questions":
        qs = db.list_questions(event_id, limit=30)
        if not qs:
            await safe_edit_or_send(update, context, txt("questions_none"), reply_markup=kb_admin_view(event_id, user_id))
            return
        lines = []
        for qx in qs:
            ts = (qx["created_at"] or "")[:19]
            lines.append(f"• <b>{html_escape(ts)}</b> — {html_escape(qx['text'])}")
        await safe_edit_or_send(update, context, txt("questions_title", title=title, value="\n".join(lines)), reply_markup=kb_admin_view(event_id, user_id))
        return

    if data == "admin:feedback":
        summ = db.get_feedback_summary(event_id)
        comments = db.list_feedback_comments(event_id, limit=10)
        value = (
            f"👍 Positive: <b>{summ['up']}</b>\n"
            f"👎 Negative: <b>{summ['down']}</b>\n"
            f"Total ratings: <b>{summ['total']}</b>\n"
        )
        if comments:
            value += "\n<b>Recent comments:</b>\n"
            for c in comments:
                emoji = "👍" if c["rating"] == 1 else "👎"
                value += f"{emoji} {html_escape(c['comment'])}\n"
        await safe_edit_or_send(update, context, txt("feedback_title", title=title, value=value), reply_markup=kb_admin_view(event_id, user_id))
        return

    if data == "admin:invite":
        link = invite_link_for(context, event_id)
        share = "https://t.me/share/url?" + urllib.parse.urlencode({"url": link, "text": ""})
        rows = [
            [InlineKeyboardButton("📤 Share", url=share)],
            [InlineKeyboardButton(btn("back"), callback_data="admin:back_to_menu")],
        ]
        await safe_edit_or_send(update, context, txt("invite_title", title=title), reply_markup=InlineKeyboardMarkup(rows))
        return


    if data == "admin:delete":
        await safe_edit_or_send(update, context, txt("delete_confirm"), reply_markup=kb_confirm("admin:delete_yes", "admin:back_to_menu"))
        return

    if data == "admin:delete_yes":
        db.delete_event(event_id)
        set_current_event_id(user_id, None)
        await safe_edit_or_send(update, context, txt("event_deleted"))
        return

    if data == "admin:back_to_menu":
        await show_event_menu(update, context, event_id, src="hub_admin")
        return

    await safe_edit_or_send(update, context, txt("unknown_action"))


# ----------------------------
# Participant actions
# ----------------------------
async def handle_participant_action(update: Update, context: ContextTypes.DEFAULT_TYPE, event_id: str, data: str):
    user = update.effective_user
    user_id = user.id
    event = db.get_event(event_id)
    title = html_escape(event["event_name"])

    if data == "p:info":
        await send_event_info_with_photos(update, context, event_id)
        return

    
    # ✅ participant share invite (share only)
    if data == "p:share":
        link = invite_link_for(context, event_id)
        share = "https://t.me/share/url?" + urllib.parse.urlencode({"url": link, "text": ""})
        rows = [
            [InlineKeyboardButton(btn("share"), url=share)],
            [InlineKeyboardButton(btn("back"), callback_data="p:back_to_menu")],
        ]
        await safe_edit_or_send(update, context, txt("invite_title", title=title), reply_markup=InlineKeyboardMarkup(rows))
        return


    if data == "p:ask":
        db.set_user_state(user_id, "p_ask_question", {"event_id": event_id})
        await safe_edit_or_send(update, context, txt("ask_question_prompt", title=title), reply_markup=kb_cancel("p:back_to_menu"))
        return

    if data == "p:feedback":
        rows = [
            [InlineKeyboardButton(btn("positive"), callback_data="p:rate:1"), InlineKeyboardButton(btn("negative"), callback_data="p:rate:-1")],
            [InlineKeyboardButton(btn("back"), callback_data="p:back_to_menu")],
        ]
        await safe_edit_or_send(update, context, txt("rating_choose", title=title), reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("p:rate:"):
        rating = int(data.split(":")[-1])
        db.set_feedback(event_id, user_id, rating, comment=None)
        db.set_user_state(user_id, "p_feedback_comment", {"event_id": event_id, "rating": rating})
        await safe_edit_or_send(
            update,
            context,
            txt("rating_saved_optional_comment"),
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(btn("skip"), callback_data="p:feedback_skip")],
                    [InlineKeyboardButton(btn("back"), callback_data="p:back_to_menu")],
                ]
            ),
        )
        return

    if data == "p:feedback_skip":
        db.clear_user_state(user_id)
        await safe_edit_or_send(update, context, txt("feedback_saved"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(btn("back"), callback_data="p:back_to_menu")]]))
        return

    if data == "p:leave":
        await safe_edit_or_send(update, context, txt("leave_confirm"), reply_markup=kb_confirm("p:leave_yes", "p:back_to_menu"))
        return

    if data == "p:leave_yes":
        db.leave_event(event_id, user_id)
        set_current_event_id(user_id, None)
        await safe_edit_or_send(update, context, txt("left_event"))
        return

    if data == "p:back_to_menu":
        await show_event_menu(update, context, event_id, src="hub_joined")
        return

    await safe_edit_or_send(update, context, txt("unknown_action"))


# ----------------------------
# Text / Photo / Contact / Location handlers
# ----------------------------
def kb_share_contact() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Share phone number", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_bot_username(context)
    user = update.effective_user
    if not user or not update.message:
        return
    user_id = user.id
    text = (update.message.text or "").strip()

    # allow /cancel typed
    cancel_cmd = "/" + cmd("cancel")
    if text.lower() in (cancel_cmd.lower(), "cancel"):
        db.clear_user_state(user_id)
        await update.message.reply_text(txt("cancelled"), parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
        return

    state, payload = db.get_user_state(user_id)

    if state == "create_event_name":
        if not text:
            await update.message.reply_text(txt("create_event_invalid_name"), parse_mode=ParseMode.HTML)
            return
        event_id = f"EV_{secrets.token_urlsafe(8)}"
        db.create_event(event_id, user_id, text)
        db.ensure_participant_stub(event_id, user_id, user.username, user.first_name, user.last_name)
        set_current_event_id(user_id, event_id)
        db.clear_user_state(user_id)
        await show_event_menu(update, context, event_id, src="hub_admin")
        return

    if state == "reg_full_name":
        eid = payload.get("event_id")
        if not eid or not db.event_exists(eid):
            db.clear_user_state(user_id)
            await update.message.reply_text(txt("event_not_found"), parse_mode=ParseMode.HTML)
            return
        if len(text) < 2:
            await update.message.reply_text(txt("reg_name_invalid"), parse_mode=ParseMode.HTML)
            return
        payload["full_name"] = text.strip()
        db.set_user_state(user_id, "reg_phone", payload)
        await update.message.reply_text(txt("reg_phone_prompt"), parse_mode=ParseMode.HTML, reply_markup=kb_share_contact())
        return

    if state == "reg_phone":
        await update.message.reply_text(txt("reg_phone_reject"), parse_mode=ParseMode.HTML, reply_markup=kb_share_contact())
        return

    if state == "reg_company":
        eid = payload.get("event_id")
        src = payload.get("src", "hub_joined")
        company = text.strip()
        if len(company) < 2:
            await update.message.reply_text(txt("reg_company_invalid"), parse_mode=ParseMode.HTML)
            return

        db.set_registration_info(
            eid,
            user_id,
            full_name=payload.get("full_name", "").strip(),
            phone=payload.get("phone_number", ""),
            company=company,
        )
        db.clear_user_state(user_id)

        await update.message.reply_text(txt("reg_saved"), parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
        await show_event_menu(update, context, eid, src=src)
        return

    current_event_id = db.get_current_event(user_id)

    if state == "admin_edit_agenda":
        eid = payload.get("event_id") or current_event_id
        if not eid or not db.is_admin(eid, user_id):
            db.clear_user_state(user_id)
            await update.message.reply_text(txt("not_allowed"), parse_mode=ParseMode.HTML)
            return
        db.set_agenda(eid, text)
        db.clear_user_state(user_id)
        await update.message.reply_text(txt("agenda_updated"), parse_mode=ParseMode.HTML)
        await show_event_menu(update, context, eid, src="hub_admin")
        return

    if state == "admin_set_time":
        eid = payload.get("event_id") or current_event_id
        dt = parse_event_time(text)
        if not dt:
            await update.message.reply_text(txt("time_invalid_format"), parse_mode=ParseMode.HTML)
            return
        db.set_time(eid, dt.isoformat(timespec="seconds"))
        db.clear_user_state(user_id)
        await update.message.reply_text(txt("time_updated"), parse_mode=ParseMode.HTML)
        await show_event_menu(update, context, eid, src="hub_admin")
        return

    if state == "admin_set_location":
        eid = payload.get("event_id") or current_event_id
        t = text.strip()
        if t.lower() == "clear":
            db.set_location(eid, None)
        else:
            db.set_location(eid, t)
        db.clear_user_state(user_id)
        await update.message.reply_text(txt("location_updated"), parse_mode=ParseMode.HTML)
        await show_event_menu(update, context, eid, src="hub_admin")
        return

    if state == "admin_set_map_pin":
        eid = payload.get("event_id") or current_event_id
        t = text.strip().lower()
        if t == "clear":
            db.clear_map_pin(eid)
            db.clear_user_state(user_id)
            await update.message.reply_text(txt("map_pin_removed"), parse_mode=ParseMode.HTML)
            await show_event_menu(update, context, eid, src="hub_admin")
            return
        await update.message.reply_text(txt("map_pin_need_location"), parse_mode=ParseMode.HTML)
        return

    if state == "admin_set_wifi":
        eid = payload.get("event_id") or current_event_id
        ssid = None
        pwd = None
        for line in text.splitlines():
            if line.lower().startswith("ssid:"):
                ssid = line.split(":", 1)[1].strip()
            if line.lower().startswith("password:"):
                pwd = line.split(":", 1)[1].strip()

        if not ssid or not pwd:
            await update.message.reply_text(txt("wifi_invalid_format"), parse_mode=ParseMode.HTML)
            return
        if len(pwd) < 8:
            await update.message.reply_text(txt("wifi_invalid_password"), parse_mode=ParseMode.HTML)
            return

        db.set_wifi(eid, ssid, pwd)
        db.clear_user_state(user_id)
        await update.message.reply_text(txt("wifi_updated"), parse_mode=ParseMode.HTML)
        await show_event_menu(update, context, eid, src="hub_admin")
        return

    if state == "admin_set_org":
        eid = payload.get("event_id") or current_event_id
        fields = {"name": "", "phone": "", "email": "", "telegram": ""}
        for line in text.splitlines():
            line = line.strip()
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            if k == "name":
                fields["name"] = v
            elif k == "phone":
                fields["phone"] = v
            elif k == "email":
                fields["email"] = v
            elif k == "telegram":
                fields["telegram"] = v

        if not fields["name"]:
            await update.message.reply_text(txt("not_allowed"), parse_mode=ParseMode.HTML)
            return

        db.set_organizer_info(eid, fields["name"], fields["phone"], fields["email"], fields["telegram"])
        db.clear_user_state(user_id)
        await update.message.reply_text(txt("org_updated"), parse_mode=ParseMode.HTML)
        await show_event_menu(update, context, eid, src="hub_admin")
        return

    if state == "admin_notify_text":
        eid = payload.get("event_id") or current_event_id
        await send_broadcast(update, context, eid, message_text=text, photo_file_id=None)
        db.clear_user_state(user_id)
        await show_event_menu(update, context, eid, src="hub_admin")
        return

    if state == "p_ask_question":
        eid = payload.get("event_id") or current_event_id
        if not eid or not db.event_exists(eid):
            db.clear_user_state(user_id)
            await update.message.reply_text(txt("event_not_found"), parse_mode=ParseMode.HTML)
            return
        db.add_question(eid, user_id, text)
        db.clear_user_state(user_id)
        await update.message.reply_text(txt("question_sent"), parse_mode=ParseMode.HTML)
        await show_event_menu(update, context, eid, src="hub_joined")
        return

    if state == "p_feedback_comment":
        eid = payload.get("event_id") or current_event_id
        rating = int(payload.get("rating", 1))
        comment = text.strip()
        if not comment:
            await update.message.reply_text(txt("comment_empty"), parse_mode=ParseMode.HTML)
            return
        db.set_feedback(eid, user_id, rating, comment=comment)
        db.clear_user_state(user_id)
        await update.message.reply_text(txt("comment_saved"), parse_mode=ParseMode.HTML)
        await show_event_menu(update, context, eid, src="hub_joined")
        return

    await update.message.reply_text(txt("use_my_events_to_continue"), parse_mode=ParseMode.HTML)


async def on_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_bot_username(context)
    user = update.effective_user
    msg = update.message
    if not user or not msg or not msg.contact:
        return

    user_id = user.id
    state, payload = db.get_user_state(user_id)
    if state != "reg_phone":
        return

    if msg.contact.user_id and msg.contact.user_id != user_id:
        await msg.reply_text(txt("share_own_contact"), parse_mode=ParseMode.HTML, reply_markup=kb_share_contact())
        return

    phone = norm_phone(msg.contact.phone_number or "")
    if not phone:
        await msg.reply_text(txt("phone_read_fail"), parse_mode=ParseMode.HTML, reply_markup=kb_share_contact())
        return

    payload["phone_number"] = phone
    db.set_user_state(user_id, "reg_company", payload)
    await msg.reply_text(txt("reg_company_prompt"), parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())


async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_bot_username(context)
    user = update.effective_user
    msg = update.message
    if not user or not msg or not msg.location:
        return

    user_id = user.id
    state, payload = db.get_user_state(user_id)
    if state != "admin_set_map_pin":
        return

    eid = payload.get("event_id") or db.get_current_event(user_id)
    if not eid or not db.is_admin(eid, user_id):
        db.clear_user_state(user_id)
        return

    lat = msg.location.latitude
    lon = msg.location.longitude
    db.set_map_pin(eid, lat, lon)

    db.clear_user_state(user_id)
    await msg.reply_text(txt("map_pin_saved"), parse_mode=ParseMode.HTML)
    await show_event_menu(update, context, eid, src="hub_admin")


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_bot_username(context)
    user = update.effective_user
    if not user or not update.message or not update.message.photo:
        return
    user_id = user.id

    state, payload = db.get_user_state(user_id)
    current_event_id = db.get_current_event(user_id)

    if state == "admin_upload_photos":
        eid = payload.get("event_id") or current_event_id
        if not eid or not db.is_admin(eid, user_id):
            db.clear_user_state(user_id)
            await update.message.reply_text(txt("not_allowed"), parse_mode=ParseMode.HTML)
            return
        photo = update.message.photo[-1]
        caption = update.message.caption
        db.add_photo(eid, photo.file_id, caption)
        await update.message.reply_text(txt("photo_saved_send_more"), parse_mode=ParseMode.HTML)
        return

    if state == "admin_notify_text":
        eid = payload.get("event_id") or current_event_id
        if not eid or not db.is_admin(eid, user_id):
            db.clear_user_state(user_id)
            return
        photo = update.message.photo[-1]
        caption = update.message.caption or ""
        await send_broadcast(update, context, eid, message_text=caption, photo_file_id=photo.file_id)
        db.clear_user_state(user_id)
        await show_event_menu(update, context, eid, src="hub_admin")
        return

    await update.message.reply_text(txt("photo_received_use_photos"), parse_mode=ParseMode.HTML)


# ----------------------------
# Broadcast / notifications
# ----------------------------
async def send_broadcast(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    event_id: str,
    message_text: str,
    photo_file_id: Optional[str] = None,
):
    event = db.get_event(event_id)
    if not event:
        await update.effective_chat.send_message(txt("event_not_found"))
        return

    admin_id = event["admin_id"]
    ids = db.get_participant_telegram_ids(event_id)
    recipient_ids = [pid for pid in ids if pid and pid != admin_id]

    if not recipient_ids:
        await update.effective_chat.send_message(txt("broadcast_none"))
        return

    prefix = "Admin of this event sent notification: "
    final_text = prefix + (message_text or "").strip()
    if not final_text.strip():
        final_text = prefix + "…"

    try:
        await update.effective_chat.send_message(txt("broadcast_sending", n=len(recipient_ids)))
    except Exception:
        pass

    success = 0
    fail = 0
    batch_size = 25
    delay = 1.0

    for i in range(0, len(recipient_ids), batch_size):
        batch = recipient_ids[i : i + batch_size]
        for pid in batch:
            try:
                if photo_file_id:
                    await context.bot.send_photo(chat_id=pid, photo=photo_file_id, caption=final_text)
                else:
                    await context.bot.send_message(chat_id=pid, text=final_text)
                success += 1
            except Exception as e:
                logger.warning(f"Broadcast failed to {pid}: {e}")
                fail += 1
        if i + batch_size < len(recipient_ids):
            await asyncio.sleep(delay)

    await update.effective_chat.send_message(txt("broadcast_done", success=success, fail=fail))


# ----------------------------
# Alerts scheduling (JobQueue)
# ----------------------------
def schedule_alert_job(app: Application, alert_id: int, event_id: str, run_at: datetime):
    try:
        app.job_queue.run_once(
            callback=job_send_alert,
            when=run_at,
            data={"alert_id": alert_id, "event_id": event_id},
            name=f"alert:{alert_id}",
        )
        logger.info(f"Scheduled alert {alert_id} for {run_at.isoformat()}")
    except Exception as e:
        logger.warning(f"Failed to schedule alert job: {e}")


async def job_send_alert(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data or {}
    alert_id = int(data.get("alert_id"))
    event_id = data.get("event_id")

    event = db.get_event(event_id)
    if not event:
        db.mark_alert_sent(alert_id)
        return

    content = db.get_event_content(event_id)
    admin_id = event["admin_id"]

    ids = db.get_participant_telegram_ids(event_id)
    recipient_ids = [pid for pid in ids if pid and pid != admin_id]
    if not recipient_ids:
        db.mark_alert_sent(alert_id)
        return

    tm = display_event_time(content.get("event_time"))
    loc = content.get("event_location") or "Not set"
    msg = (
        f"⏰ Reminder: <b>{html_escape(event['event_name'])}</b>\n"
        f"Time: <b>{html_escape(tm)}</b>\n"
        f"Location: <b>{html_escape(loc)}</b>"
    )

    for pid in recipient_ids:
        try:
            await context.bot.send_message(chat_id=pid, text=msg, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f"Alert send failed to {pid}: {e}")

    db.mark_alert_sent(alert_id)


async def post_init(application: Application):
    load_ui()
    try:
        me = await application.bot.get_me()
        application.bot_data["bot_username"] = me.username
    except Exception as e:
        logger.warning(f"get_me failed at startup: {e}")

    alerts = db.list_future_alerts()
    now = datetime.now(tz=APP_TZ)
    for a in alerts:
        try:
            run_at = datetime.fromisoformat(a["run_at_iso"])
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=APP_TZ)
            if run_at > now:
                schedule_alert_job(application, a["id"], a["event_id"], run_at)
            else:
                db.mark_alert_sent(a["id"])
        except Exception as e:
            logger.warning(f"Failed to reschedule alert {a}: {e}")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception while handling an update:", exc_info=context.error)


# ----------------------------
# Run
# ----------------------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Put it in .env as BOT_TOKEN=...")

    # Increase network timeouts (Telegram can be slow sometimes)
    request = HTTPXRequest(
        connect_timeout=30,
        read_timeout=60,
        write_timeout=30,
        pool_timeout=30,
    )

    my_defaults = Defaults(tzinfo=APP_TZ)
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .defaults(my_defaults)
        .request(request)          # ✅ timeouts applied here
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("my_events", cmd_my_events))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("cancel", cmd_cancel))

    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(MessageHandler(filters.LOCATION, on_location))
    application.add_handler(MessageHandler(filters.CONTACT, on_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    application.add_error_handler(on_error)

    logger.info("EventCompanion v2 starting…")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )




if __name__ == "__main__":
    main()

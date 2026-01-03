# EventCompanion Bot

A production-ready Telegram event management bot for organizers and participants.

## Features
- Organizer & participant roles
- Event creation & management
- Dynamic UI via `strings.json`
- Invite sharing (one-tap)
- Agenda, time, location & map pins
- Photo uploads & galleries
- Anonymous questions
- Feedback & ratings
- Scheduled alerts & broadcasts
- SQLite persistence (WAL)

## Tech stack
- Python 3.10+
- python-telegram-bot v20+
- SQLite
- Async / JobQueue

## Setup


### 1. Clone the repository
```bash
git clone https://github.com/maksudovdiiarbek/EventCompanionBot.git
cd EventCompanionBot
````

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Configuration

The bot is configured through **environment variables**.
You can set them directly in your shell or use a `.env` file (recommended).

### Required environment variables

| Variable    | Description                             | Default Value |
| ----------- | --------------------------------------- | ------------- |
| `BOT_TOKEN` | **(Required)** Your Telegram bot token. | `None`        |

### Optional environment variables

| Variable       | Description                         | Default Value        |
| -------------- | ----------------------------------- | -------------------- |
| `DB_FILE`      | Path to the SQLite database file.   | `event_companion.db` |
| `STRINGS_FILE` | Path to the UI strings JSON file.   | `strings.json`       |
| `APP_TZ`       | Application timezone (IANA format). | `Europe/Berlin`      |

### Example `.env` file

```env
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
APP_TZ=Europe/Berlin
```

> ⚠️ **Do not commit `.env` to GitHub.** It must stay private.

---

## Running the Bot

Once the environment variables are set, start the bot with:

```bash
python EventCompanionBotV2.py
```

The bot will start polling for updates from Telegram.

---

## Usage

1. Start the bot in a private chat using `/start`
2. Use `/my_events` to access your events
3. Create a new event or open an existing one
4. Share the invite link with participants
5. Manage the event via inline menus

### Organizer features

* Create and delete events
* Set agenda, time, location, WiFi, and map pin
* Upload and view photos
* Broadcast messages
* Schedule participant alerts
* View participants, questions, and feedback

### Participant features

* View event information
* Share event invite
* Ask anonymous questions
* Submit feedback
* Leave events

---

## Notes

* Participants must interact with the bot at least once before receiving messages.
* SQLite runs in WAL mode for improved concurrency.
* UI text and button labels are fully configurable via `strings.json`.

---

## Contributing

Contributions are welcome!
If you have ideas, find bugs, or want to improve the project, feel free to open an issue or submit a pull request.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
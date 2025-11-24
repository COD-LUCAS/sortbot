import os
import logging
import re
import pandas as pd
import threading
from flask import Flask

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

# Disable spam logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKEN_HERE")
FOOTER = "\n\n⚡ Powered by @codlucas"

pending_requests = {}

# ----------------------------
#  WEB SERVER (port 8080)
# ----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot running on Render Free Plan!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_web).start()

# ----------------------------
#  Fancy number pattern check
# ----------------------------

def extract_numbers_from_text(text):
    matches = re.findall(r"\+?\d{8,15}", text)
    numbers = [m.replace("+", "") for m in matches]
    return list(set(numbers))

def find_fancy_patterns(num):
    num = str(num)
    patterns = 0

    # Repeated digits
    if re.search(r"(\d)\1{2,}", num):
        patterns += 1

    # Sequential up
    if re.search(r"(0123|1234|2345|3456|4567|5678|6789)", num):
        patterns += 1

    # Sequential down
    if re.search(r"(9876|8765|7654|6543|5432|4321|3210)", num):
        patterns += 1

    # Double pattern
    if re.search(r"(\d\d)\1+", num):
        patterns += 1

    # Palindrome
    if re.search(r"(\d)(\d)\2\1", num):
        patterns += 1

    return patterns

def sort_fancy(numbers):
    scored = []
    for n in numbers:
        score = find_fancy_patterns(n)
        if score > 0:
            scored.append((n, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in scored]

# ----------------------------
# Handlers
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send a TXT / CSV / XLSX file with numbers.\n"
        "I will sort the best fancy numbers for you!"
        + FOOTER
    )

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    doc = update.message.document

    await update.message.reply_text("📥 Reading file..." + FOOTER)

    file = await doc.get_file()
    file_path = f"/tmp/{doc.file_name}"
    await file.download_to_drive(file_path)

    name = doc.file_name.lower()

    try:
        if name.endswith(".txt"):
            with open(file_path, "r") as f:
                content = f.read()
            numbers = extract_numbers_from_text(content)

        elif name.endswith(".csv"):
            df = pd.read_csv(file_path)
            content = "\n".join(df.astype(str).stack())
            numbers = extract_numbers_from_text(content)

        elif name.endswith(".xlsx"):
            df = pd.read_excel(file_path)
            content = "\n".join(df.astype(str).stack())
            numbers = extract_numbers_from_text(content)

        else:
            return await update.message.reply_text("❌ Unsupported file." + FOOTER)

        if not numbers:
            return await update.message.reply_text("❌ No numbers found." + FOOTER)

        pending_requests[user_id] = numbers

        await update.message.reply_text(
            f"📊 Found *{len(numbers)}* numbers.\n"
            "Send how many fancy numbers you want to list.\nExample: `50`"
            + FOOTER,
            parse_mode="Markdown"
        )

    except Exception as e:
        await update.message.reply_text("❌ Error: " + str(e) + FOOTER)

async def number_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    msg = update.message.text.strip()

    if not msg.isdigit():
        return
    if user_id not in pending_requests:
        return

    limit = int(msg)
    numbers = pending_requests.pop(user_id)

    await update.message.reply_text("⏳ Sorting..." + FOOTER)

    fancy = sort_fancy(numbers)

    if not fancy:
        return await update.message.reply_text("❌ No fancy numbers found." + FOOTER)

    top = fancy[:limit]

    # Build output format
    result = f"🏆 *Top {len(top)} Fancy Numbers:*\n```"
    for i, num in enumerate(top, start=1):
        if not num.startswith("+"):
            num = "+" + num
        result += f"\n{i}. {num}"
    result += "\n```" + FOOTER

    await update.message.reply_text(result, parse_mode="Markdown")

    # Remaining numbers
    if len(fancy) > limit:
        remaining_path = "/tmp/remaining.txt"
        with open(remaining_path, "w") as f:
            for n in fancy[limit:]:
                f.write("+" + n + "\n")

        await update.message.reply_document(
            document=open(remaining_path, "rb"),
            caption="📄 Remaining Fancy Numbers"
        )

# ----------------------------
# Start Bot
# ----------------------------

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, file_handler))
    app.add_handler(MessageHandler(filters.TEXT, number_input))

    app.run_polling()

if __name__ == "__main__":
    main()

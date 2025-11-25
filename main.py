import os
import logging
import re
import pandas as pd
import threading
import json
from flask import Flask
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

# -----------------------------
# CONFIG
# -----------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKEN_HERE")
OWNER_ID = 7384941543
FOOTER = "\n\n⚡ Powered by @codlucas"

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

pending_requests = {}

# -----------------------------
# USER DATABASE
# -----------------------------
def save_user(user_id):
    try:
        if not os.path.exists("users.json"):
            with open("users.json", "w") as f:
                f.write("[]")

        with open("users.json", "r") as f:
            data = json.load(f)

        if user_id not in data:
            data.append(user_id)
            with open("users.json", "w") as f:
                json.dump(data, f, indent=2)

    except Exception as e:
        print("Error saving user:", e)


# -----------------------------
# FANCY NUMBER CHECK (NO SCORE)
# -----------------------------
def extract_numbers_from_text(text):
    matches = re.findall(r"\+?\d{8,15}", text)
    return list(set(m.replace("+", "") for m in matches))

def is_fancy(num):
    num = str(num)

    if re.search(r"(.)\1{2,}", num): return True
    if re.search(r"(0123|1234|2345|3456|4567|5678|6789)", num): return True
    if re.search(r"(9876|8765|7654|6543|5432|4321|3210)", num): return True
    if re.search(r"(\d\d)\1+", num): return True
    if re.search(r"(\d)(\d)\2\1", num): return True

    return False

def filter_fancy(numbers):
    return [n for n in numbers if is_fancy(n)]


# -----------------------------
# WEB SERVER (RENDER KEEP-ALIVE)
# -----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running on Render Plan!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_web).start()


# -----------------------------
# TELEGRAM HANDLERS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.message.from_user.id)

    await update.message.reply_text(
        "👋 Send a TXT / CSV / XLSX file with numbers.\n"
        "I will extract all fancy numbers for you!"
        + FOOTER
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id != OWNER_ID:
        return await update.message.reply_text("❌ You are not authorized.")

    text = update.message.text.replace("/broadcast", "").strip()
    if not text:
        return await update.message.reply_text("Usage: /broadcast your message")

    try:
        with open("users.json", "r") as f:
            users = json.load(f)
    except:
        users = []

    sent = 0
    fail = 0

    await update.message.reply_text(f"📢 Broadcasting to {len(users)} users...")

    for uid in users:
        try:
            await context.bot.send_message(uid, text)
            sent += 1
        except:
            fail += 1

    await update.message.reply_text(
        f"✅ Broadcast Done!\n\nSent: {sent}\nFailed: {fail}"
    )


async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.message.from_user.id)

    doc = update.message.document
    user_id = update.message.from_user.id

    await update.message.reply_text("📥 Reading file..." + FOOTER)

    file = await doc.get_file()
    file_path = f"/tmp/{doc.file_name}"
    await file.download_to_drive(file_path)

    name = doc.file_name.lower()

    try:
        if name.endswith(".txt"):
            with open(file_path, "r", encoding="utf8", errors="ignore") as f:
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

        pending_requests[user_id] = numbers

        await update.message.reply_text(
            f"📊 Found *{len(numbers)}* numbers.\n"
            "Send how many fancy numbers you want.\nExample: `50`"
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

    await update.message.reply_text("⏳ Extracting fancy numbers..." + FOOTER)

    fancy = filter_fancy(numbers)

    if not fancy:
        return await update.message.reply_text("❌ No fancy numbers found." + FOOTER)

    top = fancy[:limit]

    result = f"🏆 *Top {len(top)} Fancy Numbers:*\n```"
    for i, num in enumerate(top, 1):
        result += f"\n{i}. +{num}"
    result += "\n```" + FOOTER

    await update.message.reply_text(result, parse_mode="Markdown")

    if len(fancy) > limit:
        remaining = "/tmp/remaining.txt"
        with open(remaining, "w") as f:
            for n in fancy[limit:]:
                f.write("+" + n + "\n")

        await update.message.reply_document(
            document=open(remaining, "rb"),
            caption="📄 Remaining Fancy Numbers"
        )


# -----------------------------
# START BOT
# -----------------------------
def main():
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("broadcast", broadcast))
    app_bot.add_handler(MessageHandler(filters.Document.ALL, file_handler))
    app_bot.add_handler(MessageHandler(filters.TEXT, number_input))

    app_bot.run_polling()


if __name__ == "__main__":
    main()

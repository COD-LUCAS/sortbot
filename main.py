import os
import logging
import pandas as pd
import re
from flask import Flask
import threading

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes
)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKEN_HERE")
FOOTER = "\n\n⚡ Powered by @codlucas"

pending_requests = {}

# ---------------------------
# SMALL WEB SERVER FOR RENDER
# ---------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Running!"

def run_web():
    app.run(host="0.0.0.0", port=10000)

threading.Thread(target=run_web).start()


# ---------------------------
# NUMBER EXTRACTION FUNCTIONS
# ---------------------------

def extract_numbers_from_text(text):
    numbers = []
    matches = re.findall(r"\+?\d{8,15}", text)
    for m in matches:
        numbers.append(m.replace("+", ""))  # clean +, we re-add later
    return list(set(numbers))


def find_fancy_patterns(num):
    patterns = []
    num = str(num)

    repeated = re.findall(r"(\d)\1{2,}", num)
    for m in repeated:
        patterns.append(("Repeated", m, len(m) * 10))

    seq_up = re.findall(r"(?:0123|1234|2345|3456|4567|5678|6789)", num)
    for m in seq_up:
        patterns.append(("Seq Up", m, len(m) * 8))

    seq_down = re.findall(r"(?:9876|8765|7654|6543|5432|4321|3210)", num)
    for m in seq_down:
        patterns.append(("Seq Down", m, len(m) * 8))

    double = re.findall(r"(\d\d)\1+", num)
    for m in double:
        patterns.append(("Double", m, len(m) * 6))

    pal = re.findall(r"(\d)(\d)\2\1", num)
    for m in pal:
        patterns.append(("Palindrome", "".join(m), 15))

    return patterns


def analyze_fancy(numbers):
    result = []
    for n in numbers:
        patterns = find_fancy_patterns(n)
        if patterns:
            score = sum(x[2] for x in patterns)
            result.append({"number": n, "patterns": patterns, "score": score})
    return sorted(result, key=lambda x: x["score"], reverse=True)


# ---------------------------
# HANDLERS
# ---------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send me any TXT / CSV / XLSX file containing numbers.\n"
        "I will extract & sort the *best fancy numbers*.\n" + FOOTER,
        parse_mode="Markdown"
    )


async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    document = update.message.document

    await update.message.reply_text("📥 Processing your file..." + FOOTER)

    file = await document.get_file()
    file_name = document.file_name.lower()
    path = f"/tmp/{file_name}"
    await file.download_to_drive(path)

    try:
        if file_name.endswith(".txt"):
            with open(path, "r") as f:
                content = f.read()
            numbers = extract_numbers_from_text(content)

        elif file_name.endswith(".csv"):
            df = pd.read_csv(path)
            content = "\n".join(df.astype(str).stack().tolist())
            numbers = extract_numbers_from_text(content)

        elif file_name.endswith(".xlsx"):
            df = pd.read_excel(path)
            content = "\n".join(df.astype(str).stack().tolist())
            numbers = extract_numbers_from_text(content)

        else:
            return await update.message.reply_text(
                "❌ Unsupported file type." + FOOTER
            )

        if not numbers:
            return await update.message.reply_text(
                "❌ No numbers found." + FOOTER
            )

        pending_requests[user_id] = numbers

        await update.message.reply_text(
            f"📊 Found *{len(numbers)}* numbers.\n"
            "Send how many *TOP fancy numbers* you want.\n\nExample: `50`"
            + FOOTER,
            parse_mode="Markdown"
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error: {e}" + FOOTER
        )


async def number_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    msg = update.message.text.strip()

    if not msg.isdigit():
        return
    if user_id not in pending_requests:
        return

    count = int(msg)
    numbers = pending_requests.pop(user_id)

    await update.message.reply_text("⏳ Sorting fancy numbers..." + FOOTER)

    fancy = analyze_fancy(numbers)

    if not fancy:
        return await update.message.reply_text(
            "❌ No fancy numbers found." + FOOTER
        )

    top = fancy[:count]

    # ==============================
    # FORMATTED OUTPUT EXACT STYLE
    # ==============================

    result = f"🏆 *Top {len(top)} Fancy Numbers (Best First):*\n```"

    for i, item in enumerate(top, start=1):
        num = item["number"]
        if not num.startswith("+"):
            num = "+" + num
        result += f"\n{i}. {num} (Score: {item['score']})"

    result += "\n```" + FOOTER

    await update.message.reply_text(result, parse_mode="Markdown")

    # ---- Remaining file ----
    if len(fancy) > count:
        rem_path = "/tmp/remaining.txt"
        with open(rem_path, "w") as f:
            for item in fancy[count:]:
                num = item["number"]
                if not num.startswith("+"):
                    num = "+" + num
                f.write(num + "\n")

        await update.message.reply_document(
            document=open(rem_path, "rb"),
            caption="📄 Remaining fancy numbers\n" + FOOTER
        )


# ---------------------------
# MAIN BOT RUNNER
# ---------------------------

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, file_handler))
    app.add_handler(MessageHandler(filters.TEXT, number_input))

    app.run_polling()


if __name__ == "__main__":
    main()

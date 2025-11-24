import os
import logging
import pandas as pd
import re
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKEN_HERE")

pending_requests = {}


def extract_numbers_from_text(text):
    numbers = []
    lines = text.splitlines()

    for line in lines:
        match = re.findall(r"\b\d{8,15}\b", line)
        numbers.extend(match)

    return list(set(numbers))


def find_fancy_patterns(num):
    patterns = []
    num = str(num)

    # Repeated numbers (111, 2222)
    repeated = re.findall(r"(\d)\1{2,}", num)
    for m in repeated:
        patterns.append(("Repeated Digits", m, len(m) * 10))

    # Sequential up (1234)
    seq_up = re.findall(r"(?:0123|1234|2345|3456|4567|5678|6789)", num)
    for m in seq_up:
        patterns.append(("Sequential Up", m, len(m) * 8))

    # Sequential down (9876)
    seq_down = re.findall(r"(?:9876|8765|7654|6543|5432|4321|3210)", num)
    for m in seq_down:
        patterns.append(("Sequential Down", m, len(m) * 8))

    # Double patterns (1212)
    double = re.findall(r"(\d\d)\1+", num)
    for m in double:
        patterns.append(("Double Pattern", m, len(m) * 6))

    # Palindrome (1221)
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
            result.append({
                "number": n,
                "patterns": patterns,
                "score": score,
            })

    return sorted(result, key=lambda x: x["score"], reverse=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send me any TXT / CSV / XLSX file containing numbers.\n"
        "I will sort and return the best fancy numbers!"
    )


async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    document = update.message.document

    file_path = await document.get_file()
    file_name = document.file_name.lower()

    await update.message.reply_text("📥 Downloading & processing your file...")

    download_path = f"/tmp/{file_name}"
    await file_path.download_to_drive(download_path)

    try:
        if file_name.endswith(".txt"):
            with open(download_path, "r") as f:
                text = f.read()
                numbers = extract_numbers_from_text(text)

        elif file_name.endswith(".csv"):
            df = pd.read_csv(download_path)
            text = "\n".join(df.astype(str).stack().tolist())
            numbers = extract_numbers_from_text(text)

        elif file_name.endswith(".xlsx"):
            df = pd.read_excel(download_path)
            text = "\n".join(df.astype(str).stack().tolist())
            numbers = extract_numbers_from_text(text)

        else:
            return await update.message.reply_text("❌ Unsupported file type.")

        if not numbers:
            return await update.message.reply_text("❌ No numbers found.")

        pending_requests[user_id] = numbers

        await update.message.reply_text(
            f"📊 Found *{len(numbers)}* numbers.\n"
            "Send how many top fancy numbers you want.\n\nExample: `100`",
            parse_mode="Markdown"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Error processing file: {e}")


async def number_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if not text.isdigit():
        return

    if user_id not in pending_requests:
        return

    count = int(text)
    numbers = pending_requests.pop(user_id)

    await update.message.reply_text("⏳ Analyzing fancy numbers...")

    fancy = analyze_fancy(numbers)

    if not fancy:
        return await update.message.reply_text("No fancy numbers found.")

    top = fancy[:count]

    result_text = "✨ *Top Fancy Numbers:*\n```"
    for item in top:
        result_text += f"\n{item['number']}"
    result_text += "\n```"

    await update.message.reply_text(result_text, parse_mode="Markdown")

    # Remaining
    if len(fancy) > count:
        rem_name = "remaining_fancy.txt"
        rem_path = f"/tmp/{rem_name}"

        with open(rem_path, "w") as f:
            for item in fancy[count:]:
                f.write(item["number"] + "\n")

        await update.message.reply_document(
            document=open(rem_path, "rb"),
            caption="📄 Remaining fancy numbers."
        )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, file_handler))
    app.add_handler(MessageHandler(filters.TEXT, number_input))

    app.run_polling()


if __name__ == "__main__":
    main()

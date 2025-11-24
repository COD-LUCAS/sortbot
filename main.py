import { Telegraf } from "telegraf";
import express from "express";
import fs from "fs";
import path from "path";
import multer from "multer";
import csv from "csv-parser";
import xlsx from "xlsx";
import dotenv from "dotenv";
dotenv.config();

const bot = new Telegraf(process.env.BOT_TOKEN);
const FOOTER = "\n\n⚡ Powered by @codlucas";
const pending = {};
const upload = multer({ dest: "uploads/" });

// -------------------------------------------------------
// Fancy Number Functions
// -------------------------------------------------------
function extractNumbers(text) {
    const matches = text.match(/\+?\d{8,15}/g) || [];
    return [...new Set(matches.map(n => n.replace("+", "")))];
}

function findFancyPatterns(num) {
    num = String(num);
    let score = 0;

    if (/(.)\1{2,}/.test(num)) score++; // repeated
    if (/0123|1234|2345|3456|4567|5678|6789/.test(num)) score++; // up
    if (/9876|8765|7654|6543|5432|4321|3210/.test(num)) score++; // down
    if (/(\d\d)\1+/.test(num)) score++; // double
    if (/(\d)(\d)\2\1/.test(num)) score++; // palindrome

    return score;
}

function sortFancy(numbers) {
    return numbers
        .map(n => ({ n, score: findFancyPatterns(n) }))
        .filter(obj => obj.score > 0)
        .sort((a, b) => b.score - a.score)
        .map(obj => obj.n);
}

// -------------------------------------------------------
// Telegram Handlers
// -------------------------------------------------------
bot.start(ctx =>
    ctx.reply(
        "👋 Send a TXT / CSV / XLSX file with numbers.\nI will sort the best fancy numbers for you!" + FOOTER
    )
);

bot.on("document", async ctx => {
    const userId = ctx.from.id;
    const file = await ctx.telegram.getFile(ctx.message.document.file_id);
    const fileUrl = `https://api.telegram.org/file/bot${process.env.BOT_TOKEN}/${file.file_path}`;

    const filePath = path.join("uploads", ctx.message.document.file_name);
    const writer = fs.createWriteStream(filePath);

    ctx.reply("📥 Reading file..." + FOOTER);

    const response = await fetch(fileUrl);
    const buffer = await response.arrayBuffer();
    fs.writeFileSync(filePath, Buffer.from(buffer));

    let numbers = [];

    try {
        const lower = filePath.toLowerCase();

        if (lower.endsWith(".txt")) {
            const content = fs.readFileSync(filePath, "utf8");
            numbers = extractNumbers(content);

        } else if (lower.endsWith(".csv")) {
            let text = "";
            await new Promise(resolve => {
                fs.createReadStream(filePath)
                    .pipe(csv())
                    .on("data", row => {
                        text += Object.values(row).join("\n") + "\n";
                    })
                    .on("end", resolve);
            });
            numbers = extractNumbers(text);

        } else if (lower.endsWith(".xlsx")) {
            const sheet = xlsx.readFile(filePath);
            let text = "";
            sheet.SheetNames.forEach(name => {
                text += xlsx.utils.sheet_to_csv(sheet.Sheets[name]) + "\n";
            });
            numbers = extractNumbers(text);
        } else {
            return ctx.reply("❌ Unsupported file." + FOOTER);
        }

        if (!numbers.length) {
            return ctx.reply("❌ No numbers found." + FOOTER);
        }

        pending[userId] = numbers;

        ctx.reply(
            `📊 Found *${numbers.length}* numbers.\nSend how many fancy numbers you want.\nExample: \`50\`` +
                FOOTER,
            { parse_mode: "Markdown" }
        );

    } catch (err) {
        ctx.reply("❌ Error: " + err.message + FOOTER);
    }
});

bot.on("text", async ctx => {
    const userId = ctx.from.id;
    const msg = ctx.message.text.trim();

    if (!/^\d+$/.test(msg)) return;
    if (!pending[userId]) return;

    const limit = parseInt(msg);
    const numbers = pending[userId];
    delete pending[userId];

    ctx.reply("⏳ Sorting..." + FOOTER);

    const fancy = sortFancy(numbers);

    if (!fancy.length) {
        return ctx.reply("❌ No fancy numbers found." + FOOTER);
    }

    const top = fancy.slice(0, limit);

    let out = `🏆 *Top ${top.length} Fancy Numbers:*\n\`\`\``;
    top.forEach((n, i) => (out += `\n${i + 1}. +${n}`));
    out += `\n\`\`\`${FOOTER}`;

    await ctx.reply(out, { parse_mode: "Markdown" });

    if (fancy.length > limit) {
        const remPath = "uploads/remaining.txt";
        fs.writeFileSync(remPath, fancy.slice(limit).map(n => "+" + n).join("\n"));
        await ctx.replyWithDocument({ source: remPath, filename: "remaining.txt" });
    }
});

// -------------------------------------------------------
// Express Web Server (for Railway alive)
// -------------------------------------------------------
const app = express();
app.get("/", (req, res) => res.send("Bot is running!"));
app.listen(process.env.PORT || 3000, () => console.log("Web server running"));

// -------------------------------------------------------
// Start Bot
// -------------------------------------------------------
bot.launch();
console.log("Bot started successfully!");

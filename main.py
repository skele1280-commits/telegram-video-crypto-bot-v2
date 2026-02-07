import os
import re
import uuid
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import yt_dlp

# Constants
TOKEN = os.environ.get("BOT_TOKEN")  # Set this in Replit's environment variables
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"

# Helper: Validate if input is a URL
def _is_url(text: str) -> bool:
    return bool(re.match(r"^https?://\S+$", text.strip(), re.IGNORECASE))

# Helper: Fetch top 10 by market cap + top gainer (24h % change)
def fetch_top10_and_top_gainer(vs_currency: str = "usd"):
    try:
        # Top 10 by market cap
        top10_response = requests.get(
            COINGECKO_MARKETS_URL,
            params={
                "vs_currency": vs_currency,
                "order": "market_cap_desc",
                "per_page": 10,
                "page": 1,
                "price_change_percentage": "24h",
            },
            timeout=20,
        )
        top10_response.raise_for_status()
        top10_data = top10_response.json()

        # Top gainer from a broader set (top 250 for "huge" context)
        universe_response = requests.get(
            COINGECKO_MARKETS_URL,
            params={
                "vs_currency": vs_currency,
                "order": "market_cap_desc",
                "per_page": 250,
                "page": 1,
                "price_change_percentage": "24h",
            },
            timeout=20,
        )
        universe_response.raise_for_status()
        universe_data = universe_response.json()

        # Find top gainer by 24h % change
        def pct24(item):
            v = item.get("price_change_percentage_24h")
            return v if isinstance(v, (int, float)) else float("-inf")

        top_gainer = max(universe_data, key=pct24) if universe_data else None
        return top10_data, top_gainer
    except requests.RequestException as e:
        raise Exception(f"Failed to fetch data from CoinGecko: {e}")

# Helper: Format crypto message
def format_crypto_message(top10_data, top_gainer, vs_currency: str = "USD") -> str:
    lines = []
    lines.append(f"Market Snapshot — Top 10 by Market Capitalization ({vs_currency})\n")
    for i, c in enumerate(top10_data, start=1):
        name = c.get("name", "Unknown")
        symbol = (c.get("symbol") or "").upper()
        price = c.get("current_price")
        mcap = c.get("market_cap")
        chg = c.get("price_change_percentage_24h")

        price_txt = f"${price:,.4f}" if isinstance(price, (int, float)) else "N/A"
        mcap_txt = f"${mcap:,.0f}" if isinstance(mcap, (int, float)) else "N/A"
        chg_txt = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "N/A"

        lines.append(f"{i}. {name} ({symbol}) — Price: {price_txt} | 24h Change: {chg_txt} | Market Cap: {mcap_txt}")

    lines.append("\nTop Gainer (24h) — Highlight\n")
    if top_gainer:
        g_name = top_gainer.get("name", "Unknown")
        g_symbol = (top_gainer.get("symbol") or "").upper()
        g_price = top_gainer.get("current_price")
        g_chg = top_gainer.get("price_change_percentage_24h")

        g_price_txt = f"${g_price:,.4f}" if isinstance(g_price, (int, float)) else "N/A"
        g_chg_txt = f"{g_chg:+.2f}%" if isinstance(g_chg, (int, float)) else "N/A"

        lines.append(f"{g_name} ({g_symbol}) — Price: {g_price_txt} | 24h Change: {g_chg_txt}")
    else:
        lines.append("No gainer data is available at the moment.")

    lines.append("\nPrices are indicative and may change rapidly due to live market conditions.")
    return "\n".join(lines)

# Command: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello, and welcome. This bot is currently online and ready to assist you with two services: "
        "downloading a video from a supported public URL, and displaying the latest cryptocurrency prices.\n\n"
        "Available commands:\n"
        "/download <link> — Send a valid video link and I will attempt to download and deliver the video to you.\n"
        "/crypto — View the latest top cryptocurrency prices sourced from CoinGecko.\n"
        "/updates <15m|1h|off> — Enable, disable, or adjust automatic market updates.\n\n"
        "Example:\n"
        "/download https://example.com/video\n\n"
        "For any assistance, feel free to contact the administrator."
    )

# Command: /download
async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "To proceed, please provide a video URL so I can begin processing your request. "
            "For best results, paste the full link exactly as it appears in your browser, including http:// or https://.\n\n"
            "Usage:\n"
            "/download <link>\n\n"
            "Example:\n"
            "/download https://example.com/video"
        )
        return

    url = context.args[0].strip()

    if not _is_url(url):
        await update.message.reply_text(
            "That doesn’t appear to be a valid URL. Please send a link that begins with http:// or https:// and try again."
        )
        return

    await update.message.reply_text(
        "Thank you. I have received your link and I am starting the download process now. "
        "Depending on the website, file size, and current server load, this may take a short moment."
    )

    # Generate unique filename to avoid conflicts
    file_id = uuid.uuid4().hex
    outtmpl = f"video_{file_id}.%(ext)s"

    ydl_opts = {
        "format": "mp4/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
    }

    downloaded_path = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_path = ydl.prepare_filename(info)

        with open(downloaded_path, "rb") as f:
            await update.message.reply_video(video=f)

    except Exception as e:
        await update.message.reply_text(
            "Unfortunately, I was unable to complete the download from that link. "
            "This can happen if the website blocks automated downloads, the link is private or expired, "
            "or the format is not currently supported. Please verify the URL and try again with a different link if necessary."
        )

    finally:
        # Cleanup: Remove file after sending or on error
        if downloaded_path and os.path.exists(downloaded_path):
            try:
                os.remove(downloaded_path)
            except Exception:
                pass  # Ignore cleanup errors

# Command: /crypto
async def crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Please allow a moment while I retrieve the latest market data and compile a clear snapshot of the top assets."
    )

    try:
        top10_data, top_gainer = fetch_top10_and_top_gainer("usd")
        msg = format_crypto_message(top10_data, top_gainer, "USD")
        await update.message.reply_text(msg)
    except Exception:
        await update.message.reply_text(
            "I could not retrieve market prices at the moment, most likely due to a temporary network issue or rate limiting from the data provider. "
            "Please try again shortly."
        )

# Job callback: Send scheduled crypto updates
async def send_scheduled_crypto_update(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id

    try:
        top10_data, top_gainer = fetch_top10_and_top_gainer("usd")
        msg = format_crypto_message(top10_data, top_gainer, "USD")
        await context.bot.send_message(chat_id=chat_id, text=msg)
    except Exception:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Scheduled update: market data is temporarily unavailable. I will try again on the next cycle."
        )

# Command: /updates
async def updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "To configure automatic market updates, please choose an interval.\n\n"
            "Usage:\n"
            "/updates 15m  — Receive an update every 15 minutes\n"
            "/updates 1h   — Receive an update every 1 hour\n"
            "/updates off  — Stop automatic updates"
        )
        return

    choice = context.args[0].strip().lower()
    chat_id = update.effective_chat.id

    # Remove existing jobs for this chat
    for job in context.job_queue.get_jobs_by_name(f"crypto_updates_{chat_id}"):
        job.schedule_removal()

    if choice in ("off", "stop", "disable"):
        await update.message.reply_text(
            "Automatic market updates have been disabled for this chat. You can still request a snapshot at any time using /crypto."
        )
        return

    if choice in ("15m", "15min", "15mins"):
        seconds = 15 * 60
        label = "every 15 minutes"
    elif choice in ("1h", "60m", "60min"):
        seconds = 60 * 60
        label = "every 1 hour"
    else:
        await update.message.reply_text(
            "I didn’t recognize that interval. Please use one of the following:\n"
            "/updates 15m\n"
            "/updates 1h\n"
            "/updates off"
        )
        return

    context.job_queue.run_repeating(
        send_scheduled_crypto_update,
        interval=seconds,
        first=5,  # Start shortly after enabling
        chat_id=chat_id,
        name=f"crypto_updates_{chat_id}",
    )

    await update.message.reply_text(
        f"Automatic market updates are now enabled {label}. "
        "If you would like to change the interval later, simply run /updates 15m or /updates 1h again, or use /updates off to stop."
    )

# Main application setup
if __name__ == "__main__":
    application = ApplicationBuilder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("download", download))
    application.add_handler(CommandHandler("crypto", crypto))
    application.add_handler(CommandHandler("updates", updates))

    # Run the bot
    application.run_polling()

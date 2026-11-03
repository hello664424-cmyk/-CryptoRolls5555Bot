import logging
import os
import random
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config & Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@YourChannelUsername")  # e.g. @MyCryptoChannel
DAILY_REWARD = 100
STARTING_BALANCE = 500

# In-memory database (For production, connect PostgreSQL or Redis)
users_db = {}


def get_user(user_id, username):
    """Retrieve or initialize user data."""
    if user_id not in users_db:
        users_db[user_id] = {
            "username": username or "Player",
            "balance": STARTING_BALANCE,
            "last_daily": 0,
        }
    return users_db[user_id]


async def is_subscribed(bot, user_id):
    """Check if the user is subscribed to the target Telegram Channel/Group to boost metrics."""
    if not REQUIRED_CHANNEL or REQUIRED_CHANNEL == "@YourChannelUsername":
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return True


async def check_subscription_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Gatekeeper enforcing channel join requirement before accessing casino features."""
    user = update.effective_user
    if not await is_subscribed(context.bot, user.id):
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel to Play", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton("✅ Verify Subscription", callback_data="verify_sub")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = f"🔒 **Access Restricted!**\n\nYou must join our official channel {REQUIRED_CHANNEL} to claim your daily tokens and play casino games!"
        if update.callback_query:
            await update.callback_query.message.edit_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command and render main menu."""
    user = update.effective_user
    user_data = get_user(user.id, user.username)

    if not await check_subscription_gate(update, context):
        return

    keyboard = [
        [InlineKeyboardButton("🎰 Slots", callback_data="game_slots"), InlineKeyboardButton("🎲 Dice", callback_data="game_dice")],
        [InlineKeyboardButton("🎯 Roulette", callback_data="game_roulette"), InlineKeyboardButton("💰 Daily Bonus", callback_data="daily_bonus")],
        [InlineKeyboardButton("💳 Balance", callback_data="check_balance"), InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"🎰 **Welcome to the Telegram Casino Bot!** 🎰\n\n"
        f"Hello, **{user.first_name}**!\n"
        f"💰 Current Balance: **{user_data['balance']} Chips**\n\n"
        f"Select a game below or collect your daily free chips to keep playing!"
    )

    if update.callback_query:
        await update.callback_query.message.edit_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process inline menu interactions."""
    query = update.callback_query
    user = query.from_user
    user_data = get_user(user.id, user.username)
    data = query.data

    await query.answer()

    if data == "verify_sub":
        if await is_subscribed(context.bot, user.id):
            await start(update, context)
        else:
            await query.answer("❌ You haven't joined the channel yet!", show_alert=True)
        return

    if not await check_subscription_gate(update, context):
        return

    # Balance Check
    if data == "check_balance":
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
        await query.message.edit_text(
            f"💳 **Your Account Balance**\n\nUser: @{user.username}\nBalance: **{user_data['balance']} Chips**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    # Daily Bonus Reward
    elif data == "daily_bonus":
        current_time = time.time()
        cooldown = 86400  # 24 hours
        if current_time - user_data["last_daily"] >= cooldown:
            user_data["balance"] += DAILY_REWARD
            user_data["last_daily"] = current_time
            msg = f"🎉 **Daily Reward Claimed!**\n\nYou received **+{DAILY_REWARD} Chips**!\nNew Balance: **{user_data['balance']} Chips**"
        else:
            remaining = int((cooldown - (current_time - user_data["last_daily"])) // 3600)
            msg = f"⏳ You already claimed your bonus today! Come back in **{remaining} hours**."
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # Leaderboard
    elif data == "leaderboard":
        sorted_users = sorted(users_db.values(), key=lambda x: x["balance"], reverse=True)[:5]
        board = "🏆 **Casino High Rollers Leaderboard**\n\n"
        for idx, u in enumerate(sorted_users, 1):
            board += f"{idx}. @{u['username']} — **{u['balance']} Chips**\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
        await query.message.edit_text(board, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # Native Telegram Slot Machine
    elif data == "game_slots":
        bet = 50
        if user_data["balance"] < bet:
            await query.answer("⚠️ Insufficient balance! (Cost: 50 Chips)", show_alert=True)
            return

        user_data["balance"] -= bet
        msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="🎰")
        value = msg.dice.value

        # Score evaluation for Telegram Animated Slot Machine
        # Value 64 = 777 (Jackpot), values 1, 22, 43 are 3-of-a-kind, etc.
        if value == 64:
            win = 500
            result = f"💥 **JACKPOT! 777!** You won **{win} Chips**!"
        elif value in [1, 22, 43]:
            win = 150
            result = f"🎉 **BIG WIN!** You won **{win} Chips**!"
        else:
            win = 0
            result = "❌ No match! Better luck next time."

        user_data["balance"] += win
        time.sleep(2)  # Wait for animation to finish
        
        keyboard = [
            [InlineKeyboardButton("🎰 Play Again (50 Chips)", callback_data="game_slots")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"{result}\n\n💰 New Balance: **{user_data['balance']} Chips**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    # Native Animated Dice Game
    elif data == "game_dice":
        bet = 20
        if user_data["balance"] < bet:
            await query.answer("⚠️ Insufficient balance! (Cost: 20 Chips)", show_alert=True)
            return

        user_data["balance"] -= bet
        msg = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="🎲")
        score = msg.dice.value

        if score >= 4:
            win = bet * 2
            result = f"🎲 You rolled a **{score}**! You WIN **{win} Chips**!"
        else:
            win = 0
            result = f"🎲 You rolled a **{score}**! You LOST."

        user_data["balance"] += win
        time.sleep(2)
        
        keyboard = [
            [InlineKeyboardButton("🎲 Roll Again (20 Chips)", callback_data="game_dice")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"{result}\n\n💰 New Balance: **{user_data['balance']} Chips**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    # Simple Roulette
    elif data == "game_roulette":
        keyboard = [
            [InlineKeyboardButton("🔴 Red (2x)", callback_data="bet_red"), InlineKeyboardButton("⚫ Black (2x)", callback_data="bet_black")],
            [InlineKeyboardButton("🟢 Green 0 (14x)", callback_data="bet_green")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        await query.message.edit_text("🎯 **Roulette**: Place your bet on Red, Black, or Green (Cost: 50 Chips):", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data in ["bet_red", "bet_black", "bet_green"]:
        bet = 50
        if user_data["balance"] < bet:
            await query.answer("⚠️ Insufficient balance! (Cost: 50 Chips)", show_alert=True)
            return

        user_data["balance"] -= bet
        outcome = random.choice(["red", "black", "red", "black", "red", "black", "green"])
        
        chosen = data.replace("bet_", "")
        if chosen == outcome:
            multiplier = 14 if outcome == "green" else 2
            win = bet * multiplier
            result_msg = f"🎯 Outcome: **{outcome.upper()}**! 🎉 You Won **{win} Chips**!"
            user_data["balance"] += win
        else:
            result_msg = f"🎯 Outcome: **{outcome.upper()}**! ❌ You Lost."

        keyboard = [
            [InlineKeyboardButton("🎯 Play Roulette Again", callback_data="game_roulette")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        await query.message.edit_text(
            f"{result_msg}\n\n💰 Balance: **{user_data['balance']} Chips**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "main_menu":
        await start(update, context)


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable missing!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Fallback polling start
    logger.info("Bot started successfully...")
    application.run_polling()


if __name__ == "__main__":
    main()

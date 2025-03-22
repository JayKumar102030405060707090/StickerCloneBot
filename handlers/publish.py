from pyrogram import Client, filters
from config import OWNER_ID

@Client.on_message(filters.command("promote") & filters.private)
async def promote_sticker(client, message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("❌ तुम इस कमांड को यूज़ नहीं कर सकते!")

    args = message.text.split(" ", 1)
    if len(args) < 2:
        return await message.reply_text("⚠️ Usage: `/promote <sticker_pack_name>`")

    pack_name = args[1]
    promote_link = f"https://t.me/addstickers/{pack_name}"

    await message.reply_text(f"🚀 **Sticker Pack Promotion Link:**\n{promote_link}")

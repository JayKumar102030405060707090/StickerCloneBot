from pyrogram import Client, filters
from config import OWNER_ID

@Client.on_message(filters.command("start") & filters.private)
async def start(client, message):
    if message.from_user.id == OWNER_ID:
        await message.reply_text("✅ बॉट तैयार है! अब कोई भी Sticker Pack भेजो, मैं उसे Clone कर दूंगा।")
    else:
        await message.reply_text("❌ यह बॉट सिर्फ़ Owner के लिए है!")

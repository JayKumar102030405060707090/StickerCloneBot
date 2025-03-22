from pyrogram import Client, filters
import requests

@Client.on_message(filters.sticker & filters.private)
async def clone_sticker(client, message):
    sticker_set_name = message.sticker.set_name
    if not sticker_set_name:
        await message.reply_text("❌ यह सिंगल Sticker है, कोई Sticker Pack नहीं।")
        return

    await message.reply_text(f"🔄 Cloning `{sticker_set_name}`...")

    # Telegram API से Sticker Pack Details निकालना
    sticker_set = await client.get_sticker_set(sticker_set_name)
    stickers = [s.file_id for s in sticker_set.stickers]

    new_set_name = f"cloned_{sticker_set_name}"  # नया नाम
    new_title = "My Custom Sticker Pack"  # तुम्हारा नया टाइटल

    # नया Sticker Pack बनाना
    success = await client.create_new_sticker_set(
        user_id=message.from_user.id,
        name=new_set_name,
        title=new_title,
        emojis="🔥",
        png_sticker=stickers[0]  # पहला स्टिकर जोड़ना
    )

    if success:
        await message.reply_text(f"✅ Sticker Pack Clone हुआ: [🔗 Open](https://t.me/addstickers/{new_set_name})")
    else:
        await message.reply_text("❌ Sticker Pack Clone करने में दिक्कत आई।")

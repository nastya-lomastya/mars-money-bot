"""
Kafe Gider Botu — Çalışanlar için
Kullanım: Tutar ve kategori seçerek gider ekle, makbuz fotoğrafı gönder
"""

import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("STAFF_BOT_TOKEN", "YOUR_STAFF_BOT_TOKEN")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "YOUR_SHEET_ID")
CREDENTIALS_FILE = "credentials.json"

ENTITY, AMOUNT, CATEGORY, DESCRIPTION, PAYMENT, PHOTO = range(6)
EDIT_SELECT, EDIT_FIELD, EDIT_VALUE, EDIT_CAT = range(6, 10)

ENTITIES = [
    ("🍳 Mutfak", "Mutfak"),
    ("☕ Kahvehane", "Kahvehane"),
]

SHEET_NAMES = {
    "Mutfak": "Giderler - Mutfak",
    "Kahvehane": "Giderler",
}

CATEGORIES = {
    "Mutfak": [
        ("🍋 Ürünler", "Ürünler"),
        ("🥩 Et", "Et"),
        ("➕ Diğer", "Diğer"),
    ],
    "Kahvehane": [
        ("💧 Su", "Su"),
        ("🧊 Buz", "Buz"),
        ("🐳 Su (Uludağ)", "Su (Uludağ)"),
        ("🍋 Ürünler", "Ürünler"),
        ("🥛 Süt", "Süt"),
        ("☕️ Türk Kahvesi", "Türk Kahvesi"),
        ("🧹 Temizlik", "Temizlik"),
        ("🧴 Temizlik (Ürünler)", "Temizlik (Ürünler)"),
        ("🍽️ Zuccaciye", "Zuccaciye"),
        ("📦 Karton ekipman", "Karton ekipman"),
        ("🔧 Bakım/Onarım", "Bakım/Onarım"),
        ("➕ Diğer", "Diğer"),
    ],
}

MAKBUZ_CHANNEL_ID = -1003852342555


async def send_to_channel(bot, file_bytes, filename, caption):
    """Send photo to Telegram channel and return message link"""
    try:
        msg = await bot.send_photo(
            chat_id=MAKBUZ_CHANNEL_ID,
            photo=file_bytes,
            caption=caption
        )
        # Build link to the message
        channel_id_str = str(MAKBUZ_CHANNEL_ID).replace("-100", "")
        return f"https://t.me/c/{channel_id_str}/{msg.message_id}"
    except Exception as e:
        logger.error(f"Kanal gönderme hatası: {e}")
        return ""


def get_sheet(entity="Kahvehane"):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    sheet_name = SHEET_NAMES.get(entity, "Giderler")
    try:
        ws = sheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(sheet_name, rows=1000, cols=10)
        ws.append_row(["Tarih", "Saat", "Çalışan", "Kategori", "Tutar (₺)", "Açıklama", "Ödeme", "Makbuz", "Makbuz URL", "Bot"])
    return ws


def save_expense(user_name, category, amount, description, payment, photo_url, entity="Kahvehane"):
    ws = get_sheet(entity)
    now = datetime.now()
    ws.append_row([
        now.strftime("%d.%m.%Y"),
        now.strftime("%H:%M"),
        user_name,
        category,
        amount,
        description,
        payment,
        "✅ Var" if photo_url else "❌ Yok",
        photo_url or "",
        "Çalışan Botu"
    ])
    return len(ws.get_all_values())


def get_entity_keyboard():
    keyboard = [[InlineKeyboardButton(label, callback_data=f"entity:{value}") for label, value in ENTITIES]]
    return InlineKeyboardMarkup(keyboard)


def get_category_keyboard(entity="Kahvehane"):
    keyboard = []
    row = []
    for label, value in CATEGORIES[entity]:
        row.append(InlineKeyboardButton(label, callback_data=f"cat:{value}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hoş geldin! Ben *Kafe Gider Botu*yum.\n\n"
        "📌 *Komutlar:*\n"
        "💸 /gider — Yeni gider ekle\n"
        "✏️ /duzenle — Son kaydı düzenle\n"
        "📊 /ozet — Bu ayın özeti\n"
        "📅 /gunozet — Bugünün özeti\n"
        "❌ /iptal — Mevcut işlemi iptal et\n\n"
        "Başlamak için /gider yaz!",
        parse_mode="Markdown"
    )


async def gider_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏢 *Hangi işletme için gider eklenecek?*",
        reply_markup=get_entity_keyboard(),
        parse_mode="Markdown"
    )
    return ENTITY


async def entity_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["entity"] = query.data.replace("entity:", "")
    await query.edit_message_text(
        f"✅ İşletme: *{context.user_data['entity']}*\n\n"
        f"💸 *Gider tutarını gir (₺):*\n"
        f"Örnek: `250` veya `250.50`",
        parse_mode="Markdown"
    )
    return AMOUNT


async def amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace(",", ".").strip()
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Geçersiz tutar. Lütfen sayı gir (örn: 250):")
        return AMOUNT

    context.user_data["amount"] = amount
    entity = context.user_data.get("entity", "Kahvehane")
    await update.message.reply_text(
        f"✅ İşletme: *{entity}*\n"
        f"✅ Tutar: *₺{amount:.2f}*\n\n📂 *Kategori seç:*",
        reply_markup=get_category_keyboard(entity),
        parse_mode="Markdown"
    )
    return CATEGORY


async def category_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat:", "")
    context.user_data["category"] = category
    entity = context.user_data.get("entity", "Kahvehane")
    await query.edit_message_text(
        f"✅ İşletme: *{entity}*\n"
        f"✅ Tutar: *₺{context.user_data['amount']:.2f}*\n"
        f"✅ Kategori: *{category}*\n\n"
        f"📝 *Açıklama gir:*\n"
        f"Örnek: `limon, su, peçete`",
        parse_mode="Markdown"
    )
    return DESCRIPTION


async def description_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description"] = update.message.text
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 Nakit", callback_data="pay:Nakit"),
            InlineKeyboardButton("💳 Kart", callback_data="pay:Kart"),
        ]
    ])
    await update.message.reply_text(
        f"✅ Açıklama: *{context.user_data['description']}*\n\n"
        f"💳 *Ödeme yöntemini seç:*",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return PAYMENT


async def payment_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["payment"] = query.data.replace("pay:", "")
    d = context.user_data
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📷 Makbuz fotoğrafı gönder", callback_data="wait_photo")],
        [InlineKeyboardButton("⏭️ Makbuz yok, kaydet", callback_data="no_photo")]
    ])
    await query.edit_message_text(
        f"✅ İşletme: *{d.get('entity','Kahvehane')}*\n"
        f"✅ Tutar: *₺{d['amount']:.2f}*\n"
        f"✅ Kategori: *{d['category']}*\n"
        f"✅ Açıklama: *{d['description']}*\n"
        f"✅ Ödeme: *{d['payment']}*\n\n"
        f"📷 Makbuz fotoğrafı eklemek ister misin?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return PHOTO


async def photo_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "no_photo":
        return await save_and_finish(update, context, has_photo=False)
    await query.edit_message_text("📷 Makbuz fotoğrafını gönder:")
    return PHOTO


async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_bytes = await file.download_as_bytearray()
    context.user_data["photo_bytes"] = bytes(file_bytes)
    return await save_and_finish(update, context, has_photo=True)


async def save_and_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, has_photo: bool):
    if update.callback_query:
        user = update.callback_query.from_user
        msg_func = update.callback_query.edit_message_text
    else:
        user = update.message.from_user
        msg_func = update.message.reply_text

    user_name = user.full_name or user.username or "Bilinmiyor"
    amount = context.user_data["amount"]
    category = context.user_data["category"]
    description = context.user_data["description"]
    payment = context.user_data.get("payment", "—")
    entity = context.user_data.get("entity", "Kahvehane")
    photo_bytes = context.user_data.get("photo_bytes")

    # Send to Telegram channel
    photo_url = ""
    caption = (f"🏢 {entity} | 👤 {user_name}\n"
               f"💰 ₺{amount:.2f} — {category}\n"
               f"📝 {description} | 💳 {payment}")

    if has_photo and photo_bytes:
        await msg_func("⏳ Makbuz yükleniyor...")
        photo_url = await send_to_channel(context.bot, photo_bytes, "makbuz.jpg", caption)
    else:
        # Send text-only notification to channel
        try:
            await context.bot.send_message(chat_id=MAKBUZ_CHANNEL_ID, text=f"📋 Makbuzsuz gider\n{caption}")
        except Exception as e:
            logger.error(f"Kanal mesaj hatası: {e}")

    try:
        last_row = save_expense(user_name, category, amount, description, payment, photo_url, entity)
        context.user_data.clear()
        context.user_data["last_row"] = last_row
        context.user_data["last_entity"] = entity

        await msg_func(
            f"✅ *Gider kaydedildi!*\n\n"
            f"🏢 İşletme: {entity}\n"
            f"👤 Çalışan: {user_name}\n"
            f"💰 Tutar: ₺{amount:.2f}\n"
            f"📂 Kategori: {category}\n"
            f"📝 Açıklama: {description}\n"
            f"💳 Ödeme: {payment}\n"
            f"📷 Makbuz: {'✅ Kanala gönderildi' if photo_url else '❌ Yok'}\n\n"
            f"_Düzeltmek için /duzenle yaz_",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Kayıt hatası: {e}")
        await msg_func("❌ Kayıt sırasında hata oluştu. Lütfen tekrar dene.")
        context.user_data.clear()

    return ConversationHandler.END


async def duzenle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_row = context.user_data.get("last_row")
    last_entity = context.user_data.get("last_entity", "Kahvehane")

    try:
        ws = get_sheet(last_entity)
        if not last_row:
            user_name = update.effective_user.full_name or update.effective_user.username
            records = ws.get_all_values()
            user_rows = [(i+1, r) for i, r in enumerate(records[1:], 1) if len(r) > 2 and r[2] == user_name]
            if not user_rows:
                await update.message.reply_text("❌ Düzenlenecek kayıt bulunamadı. Önce /gider ile kayıt ekle.")
                return ConversationHandler.END
            last_row, last_record = user_rows[-1]
            context.user_data["last_row"] = last_row
        else:
            last_record = ws.row_values(last_row)
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Kayıt bulunamadı.")
        return ConversationHandler.END

    r = last_record
    amount = r[4] if len(r) > 4 else "?"
    category = r[3] if len(r) > 3 else "?"
    description = r[5] if len(r) > 5 else "?"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Tutarı değiştir", callback_data="edit:amount")],
        [InlineKeyboardButton("📂 Kategoriyi değiştir", callback_data="edit:category")],
        [InlineKeyboardButton("📝 Açıklamayı değiştir", callback_data="edit:description")],
        [InlineKeyboardButton("❌ İptal", callback_data="edit:cancel")],
    ])

    await update.message.reply_text(
        f"✏️ *Son kaydını düzenle:*\n\n"
        f"💰 Tutar: ₺{amount}\n"
        f"📂 Kategori: {category}\n"
        f"📝 Açıklama: {description}\n\n"
        f"Ne değiştirmek istiyorsun?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return EDIT_FIELD


async def edit_field_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.replace("edit:", "")

    if field == "cancel":
        await query.edit_message_text("❌ İptal edildi.")
        return ConversationHandler.END

    context.user_data["edit_field"] = field

    if field == "amount":
        await query.edit_message_text("💰 Yeni tutarı gir (₺):")
        return EDIT_VALUE
    elif field == "category":
        await query.edit_message_text("📂 Yeni kategoriyi seç:", reply_markup=get_category_keyboard())
        return EDIT_CAT
    elif field == "description":
        await query.edit_message_text("📝 Yeni açıklamayı gir:")
        return EDIT_VALUE


async def edit_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data.get("edit_field")
    last_row = context.user_data.get("last_row")
    last_entity = context.user_data.get("last_entity", "Kahvehane")
    new_value = update.message.text.strip()
    col_map = {"amount": 5, "description": 6}
    col = col_map.get(field)

    if field == "amount":
        try:
            new_value = float(new_value.replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Geçersiz tutar. Tekrar gir:")
            return EDIT_VALUE

    try:
        ws = get_sheet(last_entity)
        ws.update_cell(last_row, col, new_value)
        label = "Tutar" if field == "amount" else "Açıklama"
        display = f"₺{new_value:.2f}" if field == "amount" else new_value
        await update.message.reply_text(
            f"✅ *{label} güncellendi!*\nYeni değer: *{display}*",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Güncelleme sırasında hata oluştu.")

    return ConversationHandler.END


async def edit_category_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    new_cat = query.data.replace("cat:", "")
    last_row = context.user_data.get("last_row")
    last_entity = context.user_data.get("last_entity", "Kahvehane")

    try:
        ws = get_sheet(last_entity)
        ws.update_cell(last_row, 4, new_cat)
        await query.edit_message_text(
            f"✅ *Kategori güncellendi!*\nYeni kategori: *{new_cat}*",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(e)
        await query.edit_message_text("❌ Güncelleme sırasında hata oluştu.")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_row = context.user_data.get("last_row")
    context.user_data.clear()
    if last_row:
        context.user_data["last_row"] = last_row
    await update.message.reply_text("❌ İptal edildi.")
    return ConversationHandler.END


async def send_ozet(update: Update, title, matches_fn):
    try:
        total_all = 0
        lines = [f"📊 *{title}*\n"]

        for entity_key, sheet_name in SHEET_NAMES.items():
            try:
                ws = get_sheet(entity_key)
                records = ws.get_all_records()
                filtered = [r for r in records if matches_fn(str(r.get("Tarih", "")))]
                total = sum(float(r.get("Tutar (₺)", 0)) for r in filtered)
                total_all += total
                by_cat = {}
                for r in filtered:
                    cat = r.get("Kategori", "Diğer")
                    by_cat[cat] = by_cat.get(cat, 0) + float(r.get("Tutar (₺)", 0))
                icon = "🍳" if entity_key == "Mutfak" else "☕"
                lines.append(f"{icon} *{entity_key}:* ₺{total:,.2f} ({len(filtered)} işlem)")
                for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
                    lines.append(f"  • {cat}: ₺{amt:,.2f}")
            except:
                lines.append(f"{'🍳' if entity_key == 'Mutfak' else '☕'} {entity_key}: veri yok")

        lines.append(f"\n💰 *Toplam: ₺{total_all:,.2f}*")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Özet alınamadı.")


async def ozet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    month_str = now.strftime("%m.%Y")
    await send_ozet(update, f"{now.strftime('%B %Y')} — Çalışan Giderleri", lambda tarih: tarih.endswith(month_str))


async def gunozet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    today_str = now.strftime("%d.%m.%Y")
    await send_ozet(update, f"{today_str} — Çalışan Giderleri", lambda tarih: tarih == today_str)


async def post_init(app):
    await app.bot.set_my_commands([
        BotCommand("gider", "Yeni gider ekle"),
        BotCommand("duzenle", "Son kaydı düzenle"),
        BotCommand("ozet", "Bu ayın özeti"),
        BotCommand("gunozet", "Bugünün özeti"),
        BotCommand("iptal", "Mevcut işlemi iptal et"),
    ])


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    gider_handler = ConversationHandler(
        entry_points=[CommandHandler("gider", gider_start)],
        states={
            ENTITY: [CallbackQueryHandler(entity_received, pattern="^entity:")],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_received)],
            CATEGORY: [CallbackQueryHandler(category_received, pattern="^cat:")],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description_received)],
            PAYMENT: [CallbackQueryHandler(payment_received, pattern="^pay:")],
            PHOTO: [
                CallbackQueryHandler(photo_prompt, pattern="^(wait_photo|no_photo)$"),
                MessageHandler(filters.PHOTO, photo_received),
            ],
        },
        fallbacks=[CommandHandler("iptal", cancel)],
    )

    edit_handler = ConversationHandler(
        entry_points=[CommandHandler("duzenle", duzenle_start)],
        states={
            EDIT_FIELD: [CallbackQueryHandler(edit_field_selected, pattern="^edit:")],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value_received)],
            EDIT_CAT: [CallbackQueryHandler(edit_category_received, pattern="^cat:")],
        },
        fallbacks=[CommandHandler("iptal", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ozet", ozet))
    app.add_handler(CommandHandler("gunozet", gunozet))
    app.add_handler(gider_handler)
    app.add_handler(edit_handler)

    logger.info("Çalışan botu başlatıldı...")
    app.run_polling()


if __name__ == "__main__":
    main()
"""
Kafe Gider Botu — Sahip için (Özel)
Maaşlar, vergiler ve hassas ödemeler için
"""

import os
import logging
from datetime import datetime
import pytz
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("OWNER_BOT_TOKEN", "YOUR_OWNER_BOT_TOKEN")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "YOUR_SHEET_ID")
CREDENTIALS_FILE = "credentials.json"
OWNER_CHAT_ID = int(os.environ.get("OWNER_CHAT_ID", "0"))

# Chat ID'ler — push bildirimi alacak kişiler
PUSH_CHAT_IDS = [
    8709784703,
    328286483,
    # Buraya başka chat_id ekleyebilirsin:
    # 123456789,
]

ENTITY, AMOUNT, CATEGORY, DESCRIPTION, CONFIRM = range(5)
EDIT_FIELD, EDIT_VALUE, EDIT_CAT = range(5, 8)

CATEGORIES_DEFAULT = [
    ("💼 Maaşlar", "Maaşlar"),
    ("🏛️ Maaşlar SGK", "Maaşlar SGK"),
    ("🏠 Kira", "Kira"),
    ("🍋 Ürünler", "Ürünler"),
    ("🍊 Sebze / Meyve", "Sebze / Meyve"),
    ("☕ Kahve", "Kahve"),
    ("🍵 Çay", "Çay"),
    ("💧 Su (Uludağ)", "Su (Uludağ)"),
    ("⚡ Elektrik", "Elektrik"),
    ("🔥 Doğalgaz", "Doğalgaz"),
    ("🚰 Su (Musluk)", "Su (Musluk)"),
    ("📱 Sosyal Medya", "Sosyal Medya"),
    ("🧹 Temizlik", "Temizlik"),
    ("📊 Muhasebeci", "Muhasebeci"),
    ("🔧 Bakım/Onarım", "Bakım/Onarım"),
    ("📦 Karton Ekipman (Party Outlet)", "Karton Ekipman (Party Outlet)"),
    ("⚙️ Ekipman", "Ekipman"),
    ("🍫 Chocolate", "Chocolate"),
    ("🍭 Şurup", "Şurup"),
    ("🏛️ TAX KDV", "TAX KDV"),
    ("🏛️ TAX Muhtasar", "TAX Muhtasar"),
    ("🏛️ TAX Peşin Vergi", "TAX Peşin Vergi"),
    ("🏛️ TAX SGK", "TAX SGK"),
    ("➕ Diğer", "Diğer"),
]

CATEGORIES_KISISEL = [
    ("🍋 Ürünler", "Ürünler"),
    ("☕ Cafe", "Cafe"),
    ("⚙️ Ekipman", "Ekipman"),
    ("➕ Diğer", "Diğer"),
]

CATEGORIES_BY_ENTITY = {
    "Mutfak": CATEGORIES_DEFAULT,
    "Kahvehane": CATEGORIES_DEFAULT,
    "Kişisel": CATEGORIES_KISISEL,
}


ENTITIES = [
    ("🍳 Mutfak", "Mutfak"),
    ("☕ Kahvehane", "Kahvehane"),
    ("👤 Kişisel", "Kişisel"),
]

ENTITY_ICONS = {
    "Mutfak": "🍳",
    "Kahvehane": "☕",
    "Kişisel": "👤",
}

SHEET_NAMES = {
    "Mutfak": "Sahip Giderleri - Mutfak",
    "Kahvehane": "Sahip Giderleri - Kahvehane",
    "Kişisel": "Sahip Giderleri - Kişisel",
}


def get_sheet(entity="Mutfak"):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    sheet_name = SHEET_NAMES.get(entity, "Sahip Giderleri - Mutfak")
    try:
        ws = sheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(sheet_name, rows=1000, cols=6)
        ws.append_row(["Tarih", "Saat", "Kategori", "Tutar (₺)", "Açıklama", "Bot"])
    return ws


def save_expense(category, amount, description, entity="Mutfak"):
    ws = get_sheet(entity)
    now = datetime.now()
    ws.append_row([
        now.strftime("%d.%m.%Y"),
        now.strftime("%H:%M"),
        category,
        amount,
        description,
        "Sahip Botu"
    ])
    return len(ws.get_all_values())


def get_entity_keyboard():
    keyboard = [[InlineKeyboardButton(label, callback_data=f"entity:{value}") for label, value in ENTITIES]]
    return InlineKeyboardMarkup(keyboard)


def get_category_keyboard(entity="Mutfak"):
    categories = CATEGORIES_BY_ENTITY.get(entity, CATEGORIES_DEFAULT)
    keyboard = []
    row = []
    for label, value in categories:
        row.append(InlineKeyboardButton(label, callback_data=f"cat:{value}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔒 *Sahip Botu — Özel Giderler*\n\n"
        "Maaş, vergi ve hassas ödemeler buraya kaydedilir.\n\n"
        "📌 *Komutlar:*\n"
        "💸 /gider — Yeni gider ekle\n"
        "✏️ /duzenle — Son kaydı düzenle\n"
        "📊 /ozet — Tüm giderlerin özeti\n"
        "❌ /iptal — Mevcut işlemi iptal et",
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
        f"✅ İşletme: *{context.user_data['entity']}*\n\n💸 *Gider tutarını gir (₺):*",
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
    await update.message.reply_text(
        f"✅ İşletme: *{context.user_data['entity']}*\n"
        f"✅ Tutar: *₺{amount:,.2f}*\n\n📂 *Kategori seç:*",
        reply_markup=get_category_keyboard(context.user_data.get("entity", "Mutfak")),
        parse_mode="Markdown"
    )
    return CATEGORY


async def category_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["category"] = query.data.replace("cat:", "")
    await query.edit_message_text(
        f"✅ İşletme: *{context.user_data['entity']}*\n"
        f"✅ Tutar: *₺{context.user_data['amount']:,.2f}*\n"
        f"✅ Kategori: *{context.user_data['category']}*\n\n"
        f"📝 *Açıklama gir:*\n"
        f"Örnek: `Nisan maaşı, KDV ödemesi`",
        parse_mode="Markdown"
    )
    return DESCRIPTION


async def description_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description"] = update.message.text
    d = context.user_data
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Kaydet", callback_data="confirm")],
        [InlineKeyboardButton("❌ İptal", callback_data="cancel")]
    ])
    await update.message.reply_text(
        f"📋 *Özet — Onaylıyor musun?*\n\n"
        f"🏢 İşletme: {d['entity']}\n"
        f"💰 Tutar: ₺{d['amount']:,.2f}\n"
        f"📂 Kategori: {d['category']}\n"
        f"📝 Açıklama: {d['description']}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return CONFIRM


async def confirm_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ İptal edildi.")
        return ConversationHandler.END

    amount = context.user_data.get("amount")
    category = context.user_data.get("category")
    description = context.user_data.get("description")
    entity = context.user_data.get("entity", "Mutfak")
    try:
        last_row = save_expense(category, amount, description, entity)
        context.user_data.clear()
        context.user_data["last_row"] = last_row
        context.user_data["last_entity"] = entity
        await query.edit_message_text(
            f"✅ *Gider kaydedildi!*\n\n"
            f"🏢 {entity}\n"
            f"💰 ₺{amount:,.2f} — {category}\n"
            f"📝 {description}\n\n"
            f"_Düzeltmek için /duzenle yaz_",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(e)
        await query.edit_message_text("❌ Kayıt hatası. Tekrar dene.")
        context.user_data.clear()

    return ConversationHandler.END


async def duzenle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_row = context.user_data.get("last_row")
    last_entity = context.user_data.get("last_entity", "Mutfak")
    try:
        ws = get_sheet(last_entity)
        if not last_row:
            records = ws.get_all_values()
            if len(records) < 2:
                await update.message.reply_text("❌ Düzenlenecek kayıt bulunamadı. Önce /gider ile kayıt ekle.")
                return ConversationHandler.END
            last_row = len(records)
            context.user_data["last_row"] = last_row
        last_record = ws.row_values(last_row)
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Kayıt bulunamadı.")
        return ConversationHandler.END

    r = last_record
    category = r[2] if len(r) > 2 else "?"
    amount = r[3] if len(r) > 3 else "?"
    description = r[4] if len(r) > 4 else "?"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Tutarı değiştir", callback_data="edit:amount")],
        [InlineKeyboardButton("📂 Kategoriyi değiştir", callback_data="edit:category")],
        [InlineKeyboardButton("📝 Açıklamayı değiştir", callback_data="edit:description")],
        [InlineKeyboardButton("❌ İptal", callback_data="edit:cancel")],
    ])

    await update.message.reply_text(
        f"✏️ *Son kaydını düzenle:*\n\n"
        f"📂 Kategori: {category}\n"
        f"💰 Tutar: ₺{amount}\n"
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
        last_entity = context.user_data.get("last_entity", "Mutfak")
        await query.edit_message_text("📂 Yeni kategoriyi seç:", reply_markup=get_category_keyboard(last_entity))
        return EDIT_CAT
    elif field == "description":
        await query.edit_message_text("📝 Yeni açıklamayı gir:")
        return EDIT_VALUE


async def edit_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data.get("edit_field")
    last_row = context.user_data.get("last_row")
    last_entity = context.user_data.get("last_entity", "Mutfak")
    new_value = update.message.text.strip()
    col_map = {"amount": 4, "description": 5}
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
    last_entity = context.user_data.get("last_entity", "Mutfak")
    try:
        ws = get_sheet(last_entity)
        ws.update_cell(last_row, 3, new_cat)
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


async def ozet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID)
        now = datetime.now()
        month_str = now.strftime("%m.%Y")
        total_all = 0
        lines = [f"🔒 *{now.strftime('%B %Y')} — Tüm Giderler*\n"]

        try:
            ws_staff = sheet.worksheet("Giderler")
            staff_records = ws_staff.get_all_records()
            staff = [r for r in staff_records if str(r.get("Tarih", "")).endswith(month_str)]
            staff_total = sum(float(r.get("Tutar (₺)", 0)) for r in staff)
            total_all += staff_total
            lines.append(f"👥 *Çalışan giderleri:* ₺{staff_total:,.2f} ({len(staff)} işlem)")
        except:
            lines.append("👥 Çalışan giderleri: veri yok")

        for entity_key, sheet_name in SHEET_NAMES.items():
            try:
                ws_e = sheet.worksheet(sheet_name)
                records = ws_e.get_all_records()
                filtered = [r for r in records if str(r.get("Tarih", "")).endswith(month_str)]
                entity_total = sum(float(r.get("Tutar (₺)", 0)) for r in filtered)
                total_all += entity_total
                by_cat = {}
                for r in filtered:
                    cat = r.get("Kategori", "Diğer")
                    by_cat[cat] = by_cat.get(cat, 0) + float(r.get("Tutar (₺)", 0))
                icon = ENTITY_ICONS.get(entity_key, "📁")
                lines.append(f"\n{icon} *{entity_key} giderleri:* ₺{entity_total:,.2f}")
                for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
                    lines.append(f"  • {cat}: ₺{amt:,.2f}")
            except:
                lines.append(f"\n{ENTITY_ICONS.get(entity_key, '📁')} {entity_key}: veri yok")

        lines.append(f"\n💰 *TOPLAM GİDER: ₺{total_all:,.2f}*")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Özet alınamadı.")


async def send_daily_reminder(app):
    istanbul = pytz.timezone("Europe/Istanbul")
    today = datetime.now(istanbul).strftime("%d.%m.%Y")
    text = f"📋 *Bugünün giderlerini girdiniz mi?*\n\n📅 {today} tarihli harcamalarınızı unutmayın!\n\n💸 /gider"
    for chat_id in PUSH_CHAT_IDS:
        if chat_id == 0:
            continue
        try:
            await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
            logger.info(f"Hatırlatma gönderildi → {chat_id}")
        except Exception as e:
            logger.error(f"Hatırlatma gönderilemedi ({chat_id}): {e}")


async def post_init(app):
    await app.bot.set_my_commands([
        BotCommand("gider", "Yeni gider ekle"),
        BotCommand("duzenle", "Son kaydı düzenle"),
        BotCommand("ozet", "Tüm giderlerin özeti"),
        BotCommand("iptal", "Mevcut işlemi iptal et"),
    ])

    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Istanbul"))
    scheduler.add_job(
        send_daily_reminder,
        trigger="cron",
        hour=20,
        minute=0,
        args=[app],
    )
    scheduler.start()
    logger.info("Günlük hatırlatma zamanlayıcısı başlatıldı (20:00 İstanbul)")


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    gider_handler = ConversationHandler(
        entry_points=[CommandHandler("gider", gider_start)],
        states={
            ENTITY: [CallbackQueryHandler(entity_received, pattern="^entity:")],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_received)],
            CATEGORY: [CallbackQueryHandler(category_received, pattern="^cat:")],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description_received)],
            CONFIRM: [CallbackQueryHandler(confirm_received, pattern="^(confirm|cancel)$")],
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
    app.add_handler(gider_handler)
    app.add_handler(edit_handler)

    logger.info("Sahip botu başlatıldı...")
    app.run_polling()


if __name__ == "__main__":
    main()

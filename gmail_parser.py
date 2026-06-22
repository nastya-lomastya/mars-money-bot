"""
Gmail Parser — Kasa raporunu Gmail'den al ve Google Sheets'e kaydet
Her gün otomatik çalışır, marsespressocafe@gmail.com'dan gelen XLS'i işler
"""

import os
import sys
import time
import base64
import logging
import pickle
from datetime import datetime
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pandas as pd
import subprocess
import tempfile

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gmail_parser.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "YOUR_SHEET_ID")
CREDENTIALS_FILE = "credentials.json"
GMAIL_CREDENTIALS_FILE = "gmail_credentials.json"
GMAIL_TOKEN_FILE = "gmail_token.pickle"
SENDER_EMAIL = "marsespressocafe@gmail.com"

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    """Gmail API bağlantısı — OAuth2"""
    creds = None
    if os.path.exists(GMAIL_TOKEN_FILE):
        with open(GMAIL_TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                GMAIL_CREDENTIALS_FILE, GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("gmail", "v1", credentials=creds)


def get_sheet():
    """Google Sheets bağlantısı"""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)

    try:
        ws = sheet.worksheet("Gelirler")
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet("Gelirler", rows=5000, cols=9)
        ws.append_row([
            "Tarih", "Kategori", "Ürün", "Adet", "Tutar (₺)",
            "Nakit (₺)", "Kredi Kartı (₺)", "Kişi Sayısı", "Adisyon Adedi"
        ])
        # Başlık satırını formatla
        ws.format("A1:I1", {"textFormat": {"bold": True}})
        return ws

    # Mevcut tabloda "Adisyon Adedi" kolonu yoksa ekle (geriye dönük uyumluluk)
    headers = ws.row_values(1)
    if "Adisyon Adedi" not in headers:
        if ws.col_count < 9:
            ws.add_cols(9 - ws.col_count)
        ws.update_cell(1, 9, "Adisyon Adedi")
        ws.format("I1", {"textFormat": {"bold": True}})

    return ws


def sheets_call(fn, *args, **kwargs):
    """Google Sheets API çağrısını çalıştır; 429 (kota) hatasında bekleyip tekrar dene"""
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 429 and attempt < 4:
                wait = 65
                logger.warning(f"Sheets kotası doldu, {wait}s bekleniyor (deneme {attempt + 1})...")
                time.sleep(wait)
            else:
                raise


def get_existing_dates(ws):
    """Tabloda zaten kayıtlı olan tarihleri tek seferde getir (API'yi her mailde sorgulamamak için)"""
    records = ws.get_all_values()
    return {row[0] for row in records[1:] if row}


SPREADSHEETML_NS = "urn:schemas-microsoft-com:office:spreadsheet"


def _spreadsheetml_cell_value(cell_el):
    data_el = cell_el.find(f"{{{SPREADSHEETML_NS}}}Data")
    if data_el is None or data_el.text is None:
        return ""
    if data_el.get(f"{{{SPREADSHEETML_NS}}}Type") == "Number":
        try:
            return float(data_el.text)
        except ValueError:
            return data_el.text
    return data_el.text


def parse_spreadsheetml(filepath):
    """Excel 2003 XML (SpreadsheetML) formatındaki .xls eki için parser.
    POS sistemi bazı raporları .xls uzantılı ama gerçekte bu XML formatında gönderiyor;
    ne xlrd3 ne openpyxl bunu okuyabiliyor, bu yüzden ss:Index'e göre manuel matris kuruyoruz.
    """
    import xml.etree.ElementTree as ET

    with open(filepath, "rb") as f:
        raw = f.read()
    root = ET.fromstring(raw.decode("utf-8-sig"))
    table = root.find(f"{{{SPREADSHEETML_NS}}}Worksheet/{{{SPREADSHEETML_NS}}}Table")

    sparse_rows = []
    for row_el in table.findall(f"{{{SPREADSHEETML_NS}}}Row"):
        cells = {}
        col_idx = 0
        for cell_el in row_el.findall(f"{{{SPREADSHEETML_NS}}}Cell"):
            idx_attr = cell_el.get(f"{{{SPREADSHEETML_NS}}}Index")
            if idx_attr is not None:
                col_idx = int(idx_attr) - 1
            cells[col_idx] = _spreadsheetml_cell_value(cell_el)
            merge_across = cell_el.get(f"{{{SPREADSHEETML_NS}}}MergeAcross")
            col_idx += 1 + (int(merge_across) if merge_across else 0)
        sparse_rows.append(cells)

    max_col = max((max(r.keys()) for r in sparse_rows if r), default=-1) + 1
    matrix = [[r.get(c, "") for c in range(max_col)] for r in sparse_rows]
    return pd.DataFrame(matrix)


def parse_xls(filepath):
    """XLS dosyasını parse et ve yapılandırılmış veri döndür"""
    try:
        # XLS veya XML-tabanlı XLS dosyasını oku
        try:
            import xlrd3 as xlrd
            workbook = xlrd.open_workbook(filepath)
            ws = workbook.sheet_by_index(0)
            rows = [ws.row_values(rx) for rx in range(ws.nrows)]
            df = pd.DataFrame(rows)
        except Exception:
            try:
                # XLSX (zip tabanlı) — openpyxl ile dene
                df = pd.read_excel(filepath, header=None, engine="openpyxl")
            except Exception:
                # Excel 2003 SpreadsheetML (XML, .xls uzantılı ama zip/BIFF değil)
                df = parse_spreadsheetml(filepath)

        items = []
        current_category = None
        total_cash = 0
        total_card = 0
        guests = 0
        checks = 0

        # Kategori mapping
        category_map = {
            "ESPRESSO BAZLI KAHVE": "Espresso Bazlı Kahve",
            "FILTRE KAHVELER": "Filtre Kahveler",
            "SOGUK KAHVELER": "Soğuk Kahveler",
            "TURK KAHVELERI": "Türk Kahveleri",
            "SICAK ICECEKLER": "Sıcak İçecekler",
            "SOGUK ICECEKLER": "Soğuk İçecekler",
            "FROZEN": "Frozen",
            "TATLILAR": "Tatlılar",
            "YEMEKLER": "Yemekler",
        }

        for _, row in df.iterrows():
            col0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
            col1 = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""

            # Kategori satırı (col1'de kategori adı var)
            if col1.upper() in category_map:
                current_category = category_map[col1.upper()]
                continue

            # Ürün satırı (col0'da ürün adı, col9'da adet, col15'te tutar)
            if col0 and col0 not in ["nan", "NaN"] and current_category:
                try:
                    qty = row.iloc[9] if pd.notna(row.iloc[9]) else None
                    amount = row.iloc[15] if pd.notna(row.iloc[15]) else None
                    if qty and amount and float(qty) > 0:
                        items.append({
                            "category": current_category,
                            "product": col0,
                            "qty": int(float(qty)),
                            "amount": float(amount)
                        })
                except (ValueError, IndexError):
                    pass

            # Nakit
            if col0 == "NAKIT":
                try:
                    total_cash = float(row.iloc[10]) if pd.notna(row.iloc[10]) else 0
                except (ValueError, IndexError):
                    pass

            # Kredi kartı
            if col0 == "KREDI KARTI":
                try:
                    total_card = float(row.iloc[10]) if pd.notna(row.iloc[10]) else 0
                except (ValueError, IndexError):
                    pass

            # Kişi sayısı (değer col9'da değil, col8'de — etiket hücresi 0-6 arası merge'li)
            if col0 == "Kişi Sayısı":
                try:
                    guests = int(float(row.iloc[8])) if pd.notna(row.iloc[8]) else 0
                except (ValueError, IndexError):
                    pass

            # Adisyon adedi (aynı şekilde değer col8'de)
            if col0 == "Adisyon Adedi":
                try:
                    checks = int(float(row.iloc[8])) if pd.notna(row.iloc[8]) else 0
                except (ValueError, IndexError):
                    pass

        return {
            "items": items,
            "cash": total_cash,
            "card": total_card,
            "guests": guests,
            "checks": checks,
            "total": total_cash + total_card
        }

    except Exception as e:
        logger.error(f"XLS parse hatası: {e}")
        return None


def save_to_sheets(ws, date_str, data):
    """Verileri Google Sheets'e kaydet"""
    rows = []
    for item in data["items"]:
        rows.append([
            date_str,
            item["category"],
            item["product"],
            item["qty"],
            item["amount"],
            "",  # Nakit — sadece ilk satırda
            "",  # Kart — sadece ilk satırda
            "",  # Kişi — sadece ilk satırda
            ""   # Adisyon — sadece ilk satırda
        ])

    # İlk satıra özet bilgileri ekle
    if rows:
        rows[0][5] = data["cash"]
        rows[0][6] = data["card"]
        rows[0][7] = data["guests"]
        rows[0][8] = data["checks"]

    sheets_call(ws.append_rows, rows)
    logger.info(f"{date_str}: {len(rows)} ürün kaydedildi. Toplam: ₺{data['total']:,.2f}")


FILENAME_MONTHS = {
    "jan": 1, "ocak": 1,
    "feb": 2, "subat": 2, "şubat": 2,
    "mar": 3, "mart": 3,
    "apr": 4, "nisan": 4,
    "may": 5, "mayis": 5, "mayıs": 5,
    "jun": 6, "haziran": 6,
    "jul": 7, "temmuz": 7,
    "aug": 8, "agustos": 8, "ağustos": 8,
    "sep": 9, "eylul": 9, "eylül": 9,
    "oct": 10, "ekim": 10,
    "nov": 11, "kasim": 11, "kasım": 11,
    "dec": 12, "aralik": 12, "aralık": 12,
}


def guess_date_from_filename(filename, email_date_str):
    """Dosya adından tarih tahmin et ('11.06.xls', '10 june.xls' gibi).
    Belirsiz/aralık isimli dosyalarda (örn. '1-31JULY.xls', '11j.xls', '2.xls')
    yanlış tahmin yapmamak için None döner — riskli tahminden kaçınmak, eksik
    veriden daha önemli.
    """
    import re

    name = filename.rsplit(".", 1)[0].strip().lower()
    if re.search(r"\d\s*-\s*\d", name):
        return None  # aralık (örn. "1-31july", "1-15may")

    email_dt = datetime.strptime(email_date_str, "%d.%m.%Y")

    def _valid(day, month, year):
        try:
            dt = datetime(year, month, day)
        except ValueError:
            return None
        return dt if dt <= email_dt else None

    # dd.mm.yyyy
    m = re.search(r"(\d{1,2})[.\s](\d{1,2})[.\s](\d{4})", name)
    if m:
        dt = _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return dt.strftime("%d.%m.%Y") if dt else None

    # dd.mm.yy
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2})(?!\d)", name)
    if m:
        dt = _valid(int(m.group(1)), int(m.group(2)), 2000 + int(m.group(3)))
        return dt.strftime("%d.%m.%Y") if dt else None

    # dd.mm (yıl yok — mail tarihinin yılı/önceki yıl denenir)
    m = re.search(r"(?<!\d)(\d{1,2})\.(\d{1,2})(?!\d)", name)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        for year in (email_dt.year, email_dt.year - 1):
            dt = _valid(day, month, year)
            if dt:
                return dt.strftime("%d.%m.%Y")
        return None

    # gün + ay adı (örn. "10 june", "20may")
    m = re.search(r"(\d{1,2})\s*([a-zçğıöşü]+)", name)
    if m:
        day, word = int(m.group(1)), m.group(2)
        month = next((v for k, v in FILENAME_MONTHS.items() if word.startswith(k)), None)
        if month:
            for year in (email_dt.year, email_dt.year - 1):
                dt = _valid(day, month, year)
                if dt:
                    return dt.strftime("%d.%m.%Y")
        return None

    return None


def fill_missing_from_attachments(after=None):
    """Aynı gün içinde birden fazla mail/ek olan günlerde, ilk ekten sonraki diğer
    ekler hiç işlenmiyordu. Bu fonksiyon TÜM eklere bakar; dosya adından net bir
    tarih çıkarılabiliyorsa VE o tarih tabloda hâlâ yoksa ekler. Belirsiz isimli
    dosyalar (aralık, tek harf vb.) bilinçli olarak atlanır.
    """
    logger.info("Dosya adından eksik tarihleri tamamlama başlıyor...")

    service = get_gmail_service()
    ws = get_sheet()
    existing_dates = get_existing_dates(ws)

    messages = list_all_report_messages(service, after=after)
    stats = {"added": 0, "skipped_ambiguous": 0, "skipped_existing": 0,
              "no_attachment": 0, "parse_failed": 0, "error": 0}

    for i, msg in enumerate(messages, 1):
        try:
            msg_data = service.users().messages().get(userId="me", id=msg["id"]).execute()
            email_date_str = get_message_date(msg_data)
            parts = msg_data["payload"].get("parts", [])

            for part in parts:
                filename = part.get("filename", "")
                if not (filename.endswith(".xls") or filename.endswith(".xlsx")):
                    continue

                guessed_date = guess_date_from_filename(filename, email_date_str)
                if not guessed_date:
                    stats["skipped_ambiguous"] += 1
                    continue
                if guessed_date in existing_dates:
                    stats["skipped_existing"] += 1
                    continue

                att_id = part["body"].get("attachmentId")
                if not att_id:
                    stats["no_attachment"] += 1
                    continue

                att = service.users().messages().attachments().get(
                    userId="me", messageId=msg["id"], id=att_id
                ).execute()
                xls_data = base64.urlsafe_b64decode(att["data"])
                data = parse_attachment(xls_data)

                if data and data["items"]:
                    save_to_sheets(ws, guessed_date, data)
                    existing_dates.add(guessed_date)
                    stats["added"] += 1
                    logger.info(f"{guessed_date}: '{filename}' dosyasından eklendi.")
                else:
                    stats["parse_failed"] += 1

                time.sleep(0.3)
        except Exception as e:
            logger.error(f"Mail {msg['id']} işlenemedi: {e}")
            stats["error"] += 1

        if i % 25 == 0:
            logger.info(f"{i}/{len(messages)} mail tarandı... ({stats})")

    logger.info(f"Tamamlandı: {stats}")
    return stats


def get_message_date(msg_data):
    """Mail başlığından tarihi al (dd.mm.yyyy)"""
    headers = msg_data["payload"]["headers"]
    for h in headers:
        if h["name"] == "Date":
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(h["value"])
                return dt.strftime("%d.%m.%Y")
            except Exception:
                break
    return datetime.now().strftime("%d.%m.%Y")


def fetch_xls_attachment(service, msg_id, msg_data):
    """Maildeki XLS/XLSX ekini indir, ham bytes döndür (yoksa None)"""
    parts = msg_data["payload"].get("parts", [])
    for part in parts:
        filename = part.get("filename", "")
        if filename.endswith(".xls") or filename.endswith(".xlsx"):
            att_id = part["body"].get("attachmentId")
            if att_id:
                att = service.users().messages().attachments().get(
                    userId="me", messageId=msg_id, id=att_id
                ).execute()
                return base64.urlsafe_b64decode(att["data"])
    return None


def parse_attachment(xls_data):
    """Ham XLS bytes'ı geçici dosyaya yazıp parse et"""
    with tempfile.NamedTemporaryFile(suffix=".xls", delete=False, dir="/tmp") as f:
        f.write(xls_data)
        tmp_path = f.name
    try:
        return parse_xls(tmp_path)
    finally:
        os.unlink(tmp_path)


def process_message(service, ws, msg_id, existing_dates):
    """Tek bir maili işle. (date_str, status) döndürür.
    status: 'saved' | 'skipped' | 'no_attachment' | 'parse_failed'
    """
    msg_data = service.users().messages().get(userId="me", id=msg_id).execute()
    date_str = get_message_date(msg_data)

    if date_str in existing_dates:
        return date_str, "skipped"

    xls_data = fetch_xls_attachment(service, msg_id, msg_data)
    if not xls_data:
        return date_str, "no_attachment"

    data = parse_attachment(xls_data)

    if data and data["items"]:
        save_to_sheets(ws, date_str, data)
        return date_str, "saved"

    return date_str, "parse_failed"


def check_gmail():
    """Gmail'i kontrol et ve yeni raporları işle (günlük çalıştırma için)"""
    logger.info("Gmail kontrol ediliyor...")

    try:
        service = get_gmail_service()
        ws = get_sheet()
        existing_dates = get_existing_dates(ws)

        query = f"from:{SENDER_EMAIL} has:attachment"
        results = service.users().messages().list(
            userId="me", q=query, maxResults=10
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            logger.info("Yeni rapor bulunamadı.")
            return

        processed = 0
        for msg in messages:
            try:
                date_str, status = process_message(service, ws, msg["id"], existing_dates)
            except Exception as e:
                logger.error(f"Mail {msg['id']} işlenemedi: {e}")
                continue

            if status == "saved":
                existing_dates.add(date_str)
                processed += 1
            elif status == "skipped":
                logger.info(f"{date_str} zaten aktarıldı, atlanıyor.")
            elif status == "no_attachment":
                logger.warning(f"{date_str}: XLS eki bulunamadı.")
            elif status == "parse_failed":
                logger.warning(f"{date_str}: Veri parse edilemedi.")

        logger.info(f"Tamamlandı. {processed} yeni rapor işlendi.")

    except Exception as e:
        logger.error(f"Gmail kontrol hatası: {e}")


def list_all_report_messages(service, after=None):
    """Gönderenden gelen raporları sayfalama ile getir.
    after: 'YYYY/MM/DD' verilirse sadece o tarihten sonraki mailler getirilir.
    """
    query = f"from:{SENDER_EMAIL} has:attachment"
    if after:
        query += f" after:{after}"
    messages = []
    page_token = None
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=500, pageToken=page_token
        ).execute()
        messages.extend(resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return messages


def backfill_all(after=None):
    """Gelen kutusundaki TÜM Kasa raporlarını işle (geçmiş yılı tek seferde doldurmak için)"""
    logger.info("Backfill başlıyor: tüm raporlar taranıyor...")

    service = get_gmail_service()
    ws = get_sheet()
    existing_dates = get_existing_dates(ws)

    messages = list_all_report_messages(service, after=after)
    logger.info(f"{len(messages)} mail bulundu.")

    stats = {"saved": 0, "skipped": 0, "no_attachment": 0, "parse_failed": 0, "error": 0}
    for i, msg in enumerate(messages, 1):
        try:
            date_str, status = process_message(service, ws, msg["id"], existing_dates)
            stats[status] = stats.get(status, 0) + 1
            if status == "saved":
                existing_dates.add(date_str)
        except Exception as e:
            logger.error(f"Mail {msg['id']} işlenemedi: {e}")
            stats["error"] += 1

        if i % 25 == 0:
            logger.info(f"{i}/{len(messages)} işlendi... ({stats})")

        time.sleep(0.3)  # Gmail/Sheets API kotasına nazik davran

    logger.info(f"Backfill tamamlandı: {stats}")
    return stats


def repair_and_backfill(after=None):
    """Tek seferlik onarım: 'Kişi Sayısı'/'Adisyon Adedi' index hatası ve eksik
    XML formatlı raporlar yüzünden zaten kaydedilmiş günlerin misafir/adisyon
    değerlerini düzeltir, hâlâ eklenmemiş günleri normal şekilde ekler.
    after: 'YYYY/MM/DD' verilirse sadece o tarihten sonraki mailler işlenir.
    """
    logger.info("Onarım + backfill başlıyor...")

    service = get_gmail_service()
    ws = get_sheet()

    all_values = ws.get_all_values()
    date_to_row = {}
    for i, row in enumerate(all_values[1:], start=2):  # 1. satır başlık
        if row and row[0] and row[0] not in date_to_row:
            date_to_row[row[0]] = i
    existing_dates = set(date_to_row.keys())

    messages = list_all_report_messages(service, after=after)
    logger.info(f"{len(messages)} mail bulundu.")

    stats = {"fixed": 0, "saved": 0, "no_attachment": 0, "parse_failed": 0, "error": 0}
    for i, msg in enumerate(messages, 1):
        try:
            msg_data = service.users().messages().get(userId="me", id=msg["id"]).execute()
            date_str = get_message_date(msg_data)

            xls_data = fetch_xls_attachment(service, msg["id"], msg_data)
            if not xls_data:
                stats["no_attachment"] += 1
                continue

            data = parse_attachment(xls_data)
            if not data or not data["items"]:
                stats["parse_failed"] += 1
                continue

            if date_str in existing_dates:
                row_idx = date_to_row[date_str]
                sheets_call(ws.update_cell, row_idx, 8, data["guests"])
                sheets_call(ws.update_cell, row_idx, 9, data["checks"])
                stats["fixed"] += 1
            else:
                save_to_sheets(ws, date_str, data)
                existing_dates.add(date_str)
                stats["saved"] += 1
        except Exception as e:
            logger.error(f"Mail {msg['id']} işlenemedi: {e}")
            stats["error"] += 1

        if i % 25 == 0:
            logger.info(f"{i}/{len(messages)} işlendi... ({stats})")

        time.sleep(0.3)

    logger.info(f"Onarım + backfill tamamlandı: {stats}")
    return stats


def _get_since_arg():
    """--since=YYYY/MM/DD argümanını oku (verilmemişse None)"""
    for arg in sys.argv:
        if arg.startswith("--since="):
            return arg.split("=", 1)[1]
    return None


if __name__ == "__main__":
    since = _get_since_arg()
    if "--repair" in sys.argv:
        repair_and_backfill(after=since)
    elif "--fill-missing" in sys.argv:
        fill_missing_from_attachments(after=since)
    elif "--backfill" in sys.argv:
        backfill_all(after=since)
    else:
        check_gmail()

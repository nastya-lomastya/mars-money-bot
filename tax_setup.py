"""
Bir kerelik kurulum: Vergi hesaplaması için 'Kategori KDV' referans tablosu,
gider/gelir sayfalarına yardımcı kolonlar (Ay, KDV Tutarı) ve aylık
'Vergi Hesabı' tablosunu oluşturur.

Tekrar çalıştırmak güvenlidir (idempotent) — var olan yapıyı bozmadan günceller.
"""

import os
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
CREDENTIALS_FILE = "credentials.json"

# Bilinen oranlar (sohbette ve mevcut 'KDV' taslak sayfasında belirtildi).
# Boş bırakılanlar — kullanıcı tarafından doldurulacak.
KNOWN_RATES = {
    "Maaşlar": 0,
    "Maaşlar SGK": 0,
    "Kira": 0,
    "Ürünler": 0.01,
    "Ekipman": 0.20,
    "TAX KDV": 0,
    "TAX Muhtasar": 0,
    "TAX Peşin Vergi": 0,
    "TAX SGK": 0,
    "Cafe": 0.10,
    "Et": 0.01,
}

# Tüm botlardaki kategori listelerinden derlenen, tekilleştirilmiş liste
# (Su (Uludağ)/Su (Uludag) yazım farkı giderildi).
ALL_CATEGORIES = [
    "Maaşlar", "Maaşlar SGK", "Kira", "Ürünler", "Sebze / Meyve", "Kahve", "Çay",
    "Su (Uludağ)", "Elektrik", "Doğalgaz", "Su (Musluk)", "Sosyal Medya",
    "Temizlik", "Muhasebeci", "Bakım/Onarım", "Karton Ekipman (Party Outlet)",
    "Ekipman", "Chocolate", "Şurup", "TAX KDV", "TAX Muhtasar",
    "TAX Peşin Vergi", "TAX SGK", "Diğer", "Cafe", "Et", "Su", "Buz", "Süt",
    "Türk Kahvesi", "Temizlik (Ürünler)", "Zuccaciye", "Karton ekipman",
]

# Kira ve Maaşlar nakit/gayri resmi ödeniyor (vergi dairesi görmüyor).
# Maaşlar SGK resmi bordro — vergi dairesi görüyor. Diğer her şey varsayılan resmi.
UNOFFICIAL_CATEGORIES = {"Kira", "Maaşlar"}

EXPENSE_SHEETS_STAFF = ["Giderler", "Giderler - Mutfak"]  # Tarih=A Kategori=D Tutar=E -> KDV Tutarı=K, Ay=L, Resmi Tutar=M
EXPENSE_SHEETS_OWNER = [
    "Sahip Giderleri - Mutfak", "Sahip Giderleri - Kahvehane", "Sahip Giderleri - Kişisel",
]  # Tarih=A Kategori=C Tutar=D -> KDV Tutarı=G, Ay=H, Resmi Tutar=I


def get_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return gspread.authorize(creds)


def setup_kategori_kdv(sheet):
    try:
        ws = sheet.worksheet("Kategori KDV")
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet("Kategori KDV", rows=50, cols=3)

    if ws.col_count < 3:
        ws.add_cols(3 - ws.col_count)

    existing_rates = {row[0]: row[1] if len(row) > 1 else "" for row in ws.get_all_values()[1:] if row and row[0]}
    existing_resmi = {row[0]: row[2] if len(row) > 2 else "" for row in ws.get_all_values()[1:] if row and row[0]}

    rows = [["Kategori", "KDV %", "Resmi mi?"]]
    for cat in ALL_CATEGORIES:
        rate = existing_rates.get(cat) or KNOWN_RATES.get(cat, "")
        resmi = existing_resmi.get(cat) or ("Hayır" if cat in UNOFFICIAL_CATEGORIES else "Evet")
        rows.append([cat, rate, resmi])

    ws.clear()
    ws.update("A1", rows)
    ws.format("A1:C1", {"textFormat": {"bold": True}})
    print(f"Kategori KDV: {len(rows)-1} kategori yazıldı.")
    return ws


def add_helper_columns_staff(ws):
    headers = ws.row_values(1)
    if len(headers) < 12 or headers[10] != "KDV Tutarı":
        if ws.col_count < 12:
            ws.add_cols(12 - ws.col_count)
        ws.update_cell(1, 11, "KDV Tutarı")
        ws.update_cell(1, 12, "Ay")
        ws.update("K2", [["=ARRAYFORMULA(IF(A2:A=\"\",\"\",IFERROR(E2:E*VLOOKUP(D2:D,'Kategori KDV'!A:B,2,FALSE),0)))"]], raw=False)
        ws.update("L2", [["=ARRAYFORMULA(IF(A2:A=\"\",\"\",RIGHT(A2:A,4)&\"-\"&MID(A2:A,4,2)))"]], raw=False)
        print(f"{ws.title}: K (KDV Tutarı) ve L (Ay) kolonları eklendi.")
    else:
        print(f"{ws.title}: yardımcı kolonlar zaten var, atlanıyor.")

    if len(headers) < 13 or headers[12] != "Resmi Tutar":
        if ws.col_count < 13:
            ws.add_cols(13 - ws.col_count)
        ws.update_cell(1, 13, "Resmi Tutar")
        ws.update("M2", [["=ARRAYFORMULA(IF(A2:A=\"\",\"\",IF(IFERROR(VLOOKUP(D2:D,'Kategori KDV'!A:C,3,FALSE),\"Evet\")=\"Hayır\",0,E2:E)))"]], raw=False)
        print(f"{ws.title}: M (Resmi Tutar) kolonu eklendi.")
    else:
        print(f"{ws.title}: Resmi Tutar kolonu zaten var, atlanıyor.")


def add_helper_columns_owner(ws):
    headers = ws.row_values(1)
    if len(headers) < 8 or headers[6] != "KDV Tutarı":
        if ws.col_count < 8:
            ws.add_cols(8 - ws.col_count)
        ws.update_cell(1, 7, "KDV Tutarı")
        ws.update_cell(1, 8, "Ay")
        ws.update("G2", [["=ARRAYFORMULA(IF(A2:A=\"\",\"\",IFERROR(D2:D*VLOOKUP(C2:C,'Kategori KDV'!A:B,2,FALSE),0)))"]], raw=False)
        ws.update("H2", [["=ARRAYFORMULA(IF(A2:A=\"\",\"\",RIGHT(A2:A,4)&\"-\"&MID(A2:A,4,2)))"]], raw=False)
        print(f"{ws.title}: G (KDV Tutarı) ve H (Ay) kolonları eklendi.")
    else:
        print(f"{ws.title}: yardımcı kolonlar zaten var, atlanıyor.")

    if len(headers) < 9 or headers[8] != "Resmi Tutar":
        if ws.col_count < 9:
            ws.add_cols(9 - ws.col_count)
        ws.update_cell(1, 9, "Resmi Tutar")
        ws.update("I2", [["=ARRAYFORMULA(IF(A2:A=\"\",\"\",IF(IFERROR(VLOOKUP(C2:C,'Kategori KDV'!A:C,3,FALSE),\"Evet\")=\"Hayır\",0,D2:D)))"]], raw=False)
        print(f"{ws.title}: I (Resmi Tutar) kolonu eklendi.")
    else:
        print(f"{ws.title}: Resmi Tutar kolonu zaten var, atlanıyor.")


def add_helper_column_gelirler(ws):
    headers = ws.row_values(1)
    if len(headers) < 10 or headers[9] != "Ay":
        if ws.col_count < 10:
            ws.add_cols(10 - ws.col_count)
        ws.update_cell(1, 10, "Ay")
        ws.update("J2", [["=ARRAYFORMULA(IF(A2:A=\"\",\"\",RIGHT(A2:A,4)&\"-\"&MID(A2:A,4,2)))"]], raw=False)
        print(f"{ws.title}: J (Ay) kolonu eklendi.")
    else:
        print(f"{ws.title}: Ay kolonu zaten var, atlanıyor.")


def month_list(n=14):
    from datetime import datetime
    now = datetime.now()
    months = []
    y, m = now.year, now.month
    for _ in range(n):
        months.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


def setup_vergi_hesabi(sheet):
    try:
        ws = sheet.worksheet("Vergi Hesabı")
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet("Vergi Hesabı", rows=50, cols=11)

    if ws.col_count < 11:
        ws.add_cols(11 - ws.col_count)

    header = ["Ay", "Toplam Gelir", "Vergiye Tabi Gelir", "Satış KDV",
              "Toplam Gider", "Alış KDV", "Net KDV (ödenecek)", "Kâr",
              "Resmi Gider", "Resmi Kâr", "Peşin Vergi"]

    months = month_list(14)

    rows = [header]
    for ay in months:
        r = len(rows) + 1
        rows.append([
            ay,
            f"=SUMIF(Gelirler!J:J,A{r},Gelirler!E:E)",
            f"=B{r}*0.95",
            f"=C{r}*0.10",
            (f"=SUMIF(Giderler!L:L,A{r},Giderler!E:E)"
             f"+SUMIF('Giderler - Mutfak'!L:L,A{r},'Giderler - Mutfak'!E:E)"
             f"+SUMIF('Sahip Giderleri - Mutfak'!H:H,A{r},'Sahip Giderleri - Mutfak'!D:D)"
             f"+SUMIF('Sahip Giderleri - Kahvehane'!H:H,A{r},'Sahip Giderleri - Kahvehane'!D:D)"
             f"+SUMIF('Sahip Giderleri - Kişisel'!H:H,A{r},'Sahip Giderleri - Kişisel'!D:D)"),
            (f"=SUMIF(Giderler!L:L,A{r},Giderler!K:K)"
             f"+SUMIF('Giderler - Mutfak'!L:L,A{r},'Giderler - Mutfak'!K:K)"
             f"+SUMIF('Sahip Giderleri - Mutfak'!H:H,A{r},'Sahip Giderleri - Mutfak'!G:G)"
             f"+SUMIF('Sahip Giderleri - Kahvehane'!H:H,A{r},'Sahip Giderleri - Kahvehane'!G:G)"
             f"+SUMIF('Sahip Giderleri - Kişisel'!H:H,A{r},'Sahip Giderleri - Kişisel'!G:G)"),
            f"=D{r}-F{r}",
            f"=B{r}-E{r}",
            (f"=SUMIF(Giderler!L:L,A{r},Giderler!M:M)"
             f"+SUMIF('Giderler - Mutfak'!L:L,A{r},'Giderler - Mutfak'!M:M)"
             f"+SUMIF('Sahip Giderleri - Mutfak'!H:H,A{r},'Sahip Giderleri - Mutfak'!I:I)"
             f"+SUMIF('Sahip Giderleri - Kahvehane'!H:H,A{r},'Sahip Giderleri - Kahvehane'!I:I)"
             f"+SUMIF('Sahip Giderleri - Kişisel'!H:H,A{r},'Sahip Giderleri - Kişisel'!I:I)"),
            f"=C{r}-I{r}",
            f"=MAX(J{r}*0.25,0)",
        ])

    ws.clear()
    ws.update("A1", rows, raw=False)
    ws.format("A1:K1", {"textFormat": {"bold": True}})
    print(f"Vergi Hesabı: {len(rows)-1} aylık satır yazıldı.")
    return ws


def main():
    client = get_client()
    sheet = client.open_by_key(SHEET_ID)

    setup_kategori_kdv(sheet)

    for name in EXPENSE_SHEETS_STAFF:
        add_helper_columns_staff(sheet.worksheet(name))
    for name in EXPENSE_SHEETS_OWNER:
        add_helper_columns_owner(sheet.worksheet(name))
    add_helper_column_gelirler(sheet.worksheet("Gelirler"))

    setup_vergi_hesabi(sheet)

    print("\nTamamlandı.")


if __name__ == "__main__":
    main()

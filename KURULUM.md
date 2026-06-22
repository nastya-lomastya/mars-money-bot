# 🤖 Kafe Bot — Kurulum Kılavuzu

---

## Adım 1: Telegram Botlarını Oluştur

### İki bot oluşturulacak: çalışanlar için ve sahip için

1. Telegram'da **@BotFather**'a git
2. `/newbot` yaz
3. Bot adını gir → örn: `Kafe Gider Botu`
4. Kullanıcı adını gir → örn: `kafe_calisan_bot`
5. **Token'ı kopyala** → `1234567890:ABCdef...` şeklinde

Bunu iki kez tekrarla — çalışan botu ve sahip botu için.

---

## Adım 2: Google Sheets Bağlantısını Kur

### 2.1 — Google Cloud Project Oluştur
1. https://console.cloud.google.com adresine git
2. Sol üstte **"New Project"** tıkla
3. İsim ver → örn: `kafe-bot`
4. **"Create"** tıkla

### 2.2 — API'leri Etkinleştir
1. Sol menüden **"APIs & Services" → "Enable APIs"** tıkla
2. Şunları etkinleştir:
   - **Google Sheets API**
   - **Google Drive API**

### 2.3 — Service Account Oluştur
1. **"APIs & Services" → "Credentials"** tıkla
2. **"+ CREATE CREDENTIALS" → "Service account"**
3. İsim ver → örn: `kafe-bot-service`
4. **"Done"** tıkla
5. Oluşturulan service account'a tıkla
6. **"Keys"** sekmesi → **"Add Key" → "Create new key" → "JSON"**
7. Dosya indirilir → `credentials.json` olarak yeniden adlandır

### 2.4 — Google Sheets'i Hazırla
1. Yeni bir Google Sheets oluştur
2. URL'den ID'yi kopyala:
   ```
   https://docs.google.com/spreadsheets/d/[BU_KISIM_ID]/edit
   ```
3. Sayfayı service account e-postasıyla paylaş:
   - Sağ üstte **"Share"** tıkla
   - `credentials.json` içindeki `client_email` değerini yapıştır
   - **"Editor"** izni ver

---

## Adım 3: Sahip Chat ID'sini Öğren

1. Telegram'da **@userinfobot**'a git
2. `/start` yaz
3. **ID numarasını** kopyala → örn: `123456789`

---

## Adım 4: Dosyaları Kur

```
kafe_bot/
├── staff_bot.py
├── owner_bot.py
├── requirements.txt
├── credentials.json    ← Google'dan indirdiğin dosya
└── .env               ← Aşağıdaki değerlerle oluştur
```

**.env** dosyası oluştur (`.env.example`'dan kopyala):
```
STAFF_BOT_TOKEN=çalışan_bot_token
OWNER_BOT_TOKEN=sahip_bot_token
GOOGLE_SHEET_ID=sheets_id
OWNER_CHAT_ID=sahip_chat_id
```

---

## Adım 5: Bağımlılıkları Yükle ve Botu Başlat

```bash
# Python paketlerini yükle
pip install -r requirements.txt

# Terminal 1 — Çalışan botunu başlat
python staff_bot.py

# Terminal 2 — Sahip botunu başlat
python owner_bot.py
```

---

## Adım 6: Botları Test Et

### Çalışan botu:
1. Telegram'da kendi çalışan botunu bul
2. `/start` yaz
3. `/gider` yaz → tutar gir → kategori seç → açıklama yaz → kaydet
4. Google Sheets'i kontrol et — "Giderler" sayfasında satır olmalı

### Sahip botu:
1. `/start` yaz — Chat ID'yi göreceksin
2. `/gider` veya `/maas` yaz
3. Google Sheets'te "Sahip Giderleri" sayfası açılmalı

---

## Adım 7: Sunucuda Çalıştır (7/24)

Bot sürekli çalışması için bir sunucuya yüklenmeli.

### Seçenek A: Railway (Ücretsiz başlangıç)
1. https://railway.app → GitHub ile giriş yap
2. **"New Project" → "Deploy from GitHub repo"**
3. Repo'yu yükle, environment variables gir
4. İki servis ekle: `staff_bot.py` ve `owner_bot.py`

### Seçenek B: Hetzner VPS (~4€/ay, en stabil)
```bash
# VPS'te:
git clone [repo]
pip install -r requirements.txt
# credentials.json'ı kopyala
cp .env.example .env && nano .env  # değerleri doldur

# Arka planda çalıştır
nohup python staff_bot.py &
nohup python owner_bot.py &
```

---

## Komutlar Özeti

### Çalışan Botu
| Komut | Açıklama |
|-------|----------|
| `/start` | Hoş geldin mesajı |
| `/gider` | Yeni gider ekle |
| `/ozet` | Bu ayın özeti |
| `/iptal` | Mevcut işlemi iptal et |

### Sahip Botu
| Komut | Açıklama |
|-------|----------|
| `/start` | Hoş geldin + Chat ID |
| `/gider` | Yeni gider ekle |
| `/maas` | Maaş ödemesi (kısa yol) |
| `/ozet` | Tüm giderlerin özeti |

---

## Sorun Giderme

**Bot yanıt vermiyor:**
- Token'ın doğru olduğunu kontrol et
- `python staff_bot.py` çıktısında hata var mı bak

**Google Sheets'e yazılmıyor:**
- `credentials.json` doğru klasörde mi?
- Sheets sayfası service account ile paylaşıldı mı?
- Sheet ID doğru mu?

**Sahip botu "Bu bot yalnızca sahibi için" diyor:**
- `OWNER_CHAT_ID` değerini kontrol et
- `/start` yazarak gerçek ID'ni öğren

---

**Herhangi bir adımda takılırsan yardım için Claude'a sor!** 🤖

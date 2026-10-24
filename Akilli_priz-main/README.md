# 🔌 TP-Link HS110 Akıllı Priz REST API Gateway

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-316192?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

TP-Link HS110 akıllı prizleri yerel ağ üzerinden yönetmek için geliştirilmiş **REST API Gateway** uygulamasıdır. Başlangıçta salt bir CLI aracı olarak geliştirilen bu proje, artık FastAPI altyapısı, PostgreSQL veritabanı desteği ve dinamik ağ taraması (discovery) yetenekleriyle tam donanımlı bir arka uç (backend) servisine dönüşmüştür.

---

## 📋 İçindekiler

- [✨ Özellikler](#-özellikler)
- [🏗️ Mimari](#️-mimari)
- [📁 Proje Yapısı](#-proje-yapısı)
- [⚙️ Gereksinimler](#️-gereksinimler)
- [🚀 Kurulum ve Çalıştırma](#-kurulum-ve-çalıştırma)
- [📡 Ağ Taraması (Discovery) ve Cihaz Yönetimi](#-ağ-taraması-discovery-ve-cihaz-yönetimi)
- [🔌 API Kullanımı](#-api-kullanımı)
- [🔮 Gelecek Planları (Plugin Mimarisi)](#-gelecek-planları-plugin-mimarisi)
- [📄 Lisans](#-lisans)

---

## ✨ Özellikler

| Özellik | Açıklama |
|---------|----------|
| 🌐 **REST API Gateway** | Tüm cihaz kontrolleri FastAPI üzerinden HTTP uç noktalarıyla donatıldı. |
| 🗄️ **Veritabanı Entegrasyonu** | PostgreSQL kullanılarak cihazların sisteme eklenmesi, silinmesi ve güncellenmesi (CRUD) sağlandı. |
| 📡 **Ağ Taraması (Discovery)** | Yerel ağdaki prizleri otomatik bulmak için UDP Broadcast ve TCP Subnet Scan (fallback) yöntemleri geliştirildi. |
| ⚡ **Enerji ve Kontrol** | Anlık voltaj, akım, güç ölçümü ve röle (aç/kapat), LED durum kontrolleri. |
| 📶 **Wi-Fi Yönetimi** | Ağ taraması yetenekleriyle entegre olarak çevredeki Wi-Fi ağlarını listeleme ve cihaza Wi-Fi yapılandırması gönderme. |
| 🚫 **Ham Command Gateway** | Gelişmiş kullanıcılar için doğrudan TCP şifreli JSON payload'ları gönderebilme esnekliği. |

---

## 🏗️ Mimari

Proje istemci ile cihaz arasında bir köprü (gateway) görevi görür:

1. **Frontend / İstemci**: HTTP istekleriyle API'ye bağlanır.
2. **FastAPI (Gateway)**: Gelen istekleri işler, PostgreSQL veritabanından cihaz IP/MAC kayıtlarını doğrular.
3. **TCP Connection**: Cihazla yerel ağda (TCP Port 9999) `XOR Autokey` şifrelemesi kullanarak haberleşir.

---

## 📁 Proje Yapısı

```
Akilli_priz/
├── api.py               # FastAPI uygulamasının ana giriş noktası (Uvicorn ile çalışır)
├── config.py            # Ortam değişkenleri ve (CORS, DB ayarları) Pydantic konfigürasyonu
├── .env                 # Veritabanı (DATABASE_URL) ve sistem konfigürasyonları
├── core/
│   ├── discovery.py     # UDP Broadcast ve TCP subnet üzerinden cihaz keşif modülü
│   ├── device.py        # HS110 cihazıyla TCP bağlantısını kuran temel donanım sınıfı
│   └── protocol.py      # TP-Link Smart Home XOR şifreleme/çözme algoritması
├── db/
│   ├── database.py      # SQLAlchemy & asyncpg PostgreSQL bağlantı motoru
│   └── models.py        # Veritabanı tabloları (Device)
├── routes/
│   ├── control.py       # Aç/kapat, enerji, led API uç noktaları
│   ├── devices.py       # DB üzerinden cihaz CRUD uç noktaları
│   ├── discovery.py     # Ağ taramasını başlatan uç nokta
│   └── wifi.py          # Wi-Fi yapılandırma ve tarama uç noktaları
├── requirements.txt     # Bağımlılıklar (FastAPI, uvicorn, sqlalchemy, asyncpg vb.)
└── ...
```

---

## ⚙️ Gereksinimler

- **Python 3.10+** 
- **PostgreSQL** Veritabanı
- TP-Link HS110 Akıllı Priz (Aynı yerel ağda)

Bağımlılıklar: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `pydantic-settings`, `python-dotenv`.

---

## 🚀 Kurulum ve Çalıştırma

### 1. Ortamın Hazırlanması

```bash
# Repoyu klonlayın
git clone https://github.com/CodebyCodef/Akilli_priz.git
cd Akilli_priz

# Sanal ortam oluşturup aktif edin
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Gerekli kütüphaneleri yükleyin
pip install -r requirements.txt
```

### 2. Veritabanı Konfigürasyonu

Ana dizinde bir `.env` dosyası oluşturun (veya mevcut dosyayı düzenleyin) ve PostgreSQL bağlantı URI'nizi girin:

```env
DATABASE_URL=postgresql+asyncpg://kullanici_adi:sifre@localhost/hs110_db
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

*(Not: API veritabanı olmadan da ayağa kalkabilir ancak cihaz kayıt (CRUD) işlemleri hata verecektir.)*

### 3. API'yi Başlatma

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Sunucu başladığında tarayıcınızdan **[http://localhost:8000/docs](http://localhost:8000/docs)** adresine giderek Swagger UI üzerinden tüm uç noktaları test edebilirsiniz.

---

## 📡 Ağ Taraması (Discovery) ve Cihaz Yönetimi

Projedeki en büyük yeniliklerden biri dinamik ağ taramasıdır. Sistem çevredeki prizleri bulmak için çok katmanlı bir yöntem kullanır:

1. **UDP Broadcast (`10.141.5.255:9999` vs):** Tüm ağa şifreli bir kimlik sorma paketi yollar. Saniyeler içinde yanıt alınmasını sağlar.
2. **TCP Subnet Scan:** UDP'nin firewall/router tarafından engellendiği ağlarda otomatik devreye girer. İşletim sisteminin ARP tablosunu ve aktif ağ bağdaştırıcılarının alt ağlarını (`/24`) tarayarak prizleri milisaniyeler içinde asenkron olarak pingler.

Bulunan bu cihazlar API üzerinden otomatik / manuel olarak sisteme (veritabanına) eklenebilir, IP'leri güncellenebilir veya silinebilir. Cihazlara yeni Wi-Fi konfigürasyonları kolayca atanabilir.

---

## 🔌 API Kullanımı

API dökümantasyonu tam olarak kod içerisine gömülüdür ancak ana router'lar şu şekildedir:

- `GET /discover` -> Ağdaki prizleri tarar.
- `GET /devices`, `POST /devices`, `DELETE /devices/{id}` -> CRUD işlemleri.
- `POST /control/{device_id}/on`, `POST /control/{device_id}/off` -> Güç kontrolü.
- `GET /control/{device_id}/energy` -> Anlık tüketim (A, V, W).
- `GET /wifi/{device_id}/scan`, `POST /wifi/{device_id}/connect` -> Ağ ayarları.


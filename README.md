
<div align="center">

<img src="banner.png" alt="myAgent" width="672"/>

### Claude Düşünür — Gemini Çalışır — Siz Sadece Hedeflersiniz

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Claude](https://img.shields.io/badge/Brain-Claude%203.5-c084fc?style=flat-square)
![Gemini](https://img.shields.io/badge/Hands-Gemini%202.0-4285F4?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-6D28D9?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)

**myAgent**, dünyanın en gelişmiş iki yapay zeka modelini (Claude ve Gemini) tek bir otonom döngüde birleştiren, yüksek performanslı bir AI Terminal asistanıdır.

</div>

---

## 💡 Felsefe: Bilinçli Asimetri

Piyasadaki AI ajanlarının çoğu "pahalı" modelleri her basit dosya okuma işlemi için kullanarak bütçenizi ve limitlerinizi hızla tüketir. **myAgent** farklıdır:

> **Stratejik Zekayı** (Planlama ve İnceleme) Claude'a verir, **Kas Gücünü** (Kod Yazma ve Terminal Yürütme) Gemini'ye bırakır.

Bu asimetrik mimari sayesinde Claude Code ile aynı projeyi ayağa kaldırırken **token maliyetinden %90'a kadar tasarruf** edersiniz. Claude sadece planlar ve review yapar (az token), Gemini binlerce satır kodu ücretsiz/ucuz bağlamında yazar.

---

## 🖥️ Yeni Nesil TUI (Terminal Kullanıcı Arayüzü)

`tui_features` dalı ile gelen yenilikler, myAgent'ı bir komut satırı aracından tam teşekküllü bir **AI-IDE** deneyimine dönüştürdü.

<div align="center">
<img src="docs/tui_mockup.svg" alt="myAgent Modern TUI" width="800"/>
<br/><em>Yeni nesil üç panelli responsive arayüz</em>
</div>

### Öne Çıkan UX Özellikleri:

*   **Canlı Takip Paneli (Ctrl+E):** Sağ panelde Claude'un stratejik adımlarını ve Gemini'nin canlı loglarını (ruff, pytest, bash) anlık izleyin.
*   **Entegre Dosya Gezgini (Ctrl+B):** Sol panelde proje yapısını görün, dizinler arasında gezinin. Ekran daraldığında otomatik gizlenir.
*   **Kelime Seçim Modu (Ctrl+K):** Terminalin seçim kısıtlamalarından kurtulun. Tüm geçmişi seçilebilir ve kopyalanabilir bir alanda yönetin.
*   **Anlık Ayarlar (Ctrl+S):** Uygulamadan çıkmadan modelleri değiştirin, API anahtarlarını güncelleyin ve modları (Auto-approve, Dry-run) yönetin.
*   **Human-in-the-Loop:** Claude planı bitirdiğinde onayınızı bekler. Siz "Yürü" diyene kadar hiçbir dosya değişmez.

---

## 🧠 Otonom Güç: Aşama 6 Döngüsü

myAgent artık sadece kod yazmıyor, projenizi bir mühendis gibi "araştırıyor" ve "hata yapınca durup düşünüyor".

<div align="center">
  <img src="docs/feature_autonomy.svg" width="400" alt="Otonom Döngü"/>
  <img src="docs/feature_search.svg" width="400" alt="Derin Arama"/>
</div>

### 1. Derin Arama (Deep Search / ripgrep)
`ripgrep` entegrasyonu sayesinde Claude, plan yapmadan önce tüm projeyi (milyonlarca satır olsa bile) milisaniyeler içinde tarar. Sizin sadece dosya ismini vermeniz yeterlidir; myAgent ilgili kodları bulur ve bağlamına ekler.

### 2. Gözlem Mekanizması (Observation)
Gemini bir engelle karşılaştığında (örn: bir dosya planlanan yerde değilse veya bir kütüphane eksikse) sadece hata vermez. Durumu analiz eder ve Claude'a bir **OBSERVATION** raporu sunar. Claude bu rapora göre stratejisini anında günceller.

### 3. Kendi Kendini İyileştirme (Self-Healing)
Reviewer katmanı (Linter ve Testler) hata bulduğunda, sistem otonom bir düzeltme döngüsüne girer. Testler geçene kadar (veya maksimum tur dolana kadar) Gemini ve Claude paslaşarak kodu mükemmelleştirir.

---

## 🚀 Mimari Akış

```mermaid
flowchart TD
    User(["👤 Sen"])

    subgraph claude ["🟣 Claude 3.5 — Brain (Planner & Reviewer)"]
        Search["**Deep Search (rg)**
Arama & Araştırma"]
        Planner["**Strategic Planner**
Atomik Adımlar"]
        Reviewer["**Code Reviewer**
Linter & Test Kontrol"]
    end

    subgraph gemini ["🔵 Gemini 2.0 — Hands (Worker)"]
        Worker["**The Executor**
FILE / BASH Otonomisi"]
    end

    User -->|Görev| Search
    Search --> Planner
    Planner -->|Plan| Approval{🤔 Onay?}
    Approval -->|Evet| Worker
    Approval -->|Hayır| User
    Worker -->|Observation| Planner
    Worker --> Reviewer
    Reviewer -->|Hata Varsa| Worker
    Reviewer -->|Temiz| User
```

---

## ⌨️ Klavye Kısayolları

| Tuş | Fonksiyon |
|---|---|
| **`Ctrl+B`** | **Dosya Gezgini'ni (Sol Panel) aç / kapat** |
| **`Ctrl+E`** | **İşlem Takibi'ni (Sağ Panel) aç / kapat** |
| **`Ctrl+K`** | **Kelime Seçim Modu (Seç & Kopyala)** |
| **`Ctrl+S`** | **Ayarlar Modalını aç** |
| `Ctrl+L` | Ekranı ve logları temizle |
| `Ctrl+Y` | Son AI cevabını panoya kopyala |
| `↑` / `↓` | Komut geçmişinde gezin |
| `Tab` | Komutları otomatik tamamla |
| `F1` | Yardım menüsünü göster |
| `Ctrl+C` | Durdur / Çıkış (Güvenli autosave) |

---

## 📦 Kurulum ve Çalıştırma

### A — Docker (Önerilen - En Güçlü Mod)
*Bu modda ajan tam otonomi (`sed`, `g++` vb. izinleri) ile çalışır ve sisteminizden izole kalır.*

```bash
git checkout tui_features
docker compose build
./run.sh
```

### B — Lokal venv (Hızlı Mod)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
python -m myagent
```

---

## 🛠️ Teknik Özellikler

- **Responsive TUI:** Ekran boyutuna göre otomatik düzenlenen arayüz (Auto-collapse).
- **Git Checkpoint:** Büyük değişiklikler öncesi otomatik durum kaydı ve geri alma desteği.
- **Token Tracker:** Anlık maliyet analizi ve "Tümü Claude olsaydı" karşılaştırması.
- **Docker Sandbox:** Tehlikeli komutlar için tam güvenlikli kum havuzu.

<div align="center">

---

*Claude Düşünür. Gemini Çalışır. myAgent Yönetir.*

</div>

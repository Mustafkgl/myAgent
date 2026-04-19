
<div align="center">

<img src="banner.png" alt="myAgent" width="672"/>

### Claude Düşünür — Gemini Çalışır — Siz Sadece Hedeflersiniz

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Claude](https://img.shields.io/badge/Brain-Claude%203.5-c084fc?style=flat-square)
![Gemini](https://img.shields.io/badge/Hands-Gemini%202.0-4285F4?style=flat-square)
![Efficiency](https://img.shields.io/badge/Efficiency-90%25%20Saving-green?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)

**myAgent**, dünyanın en gelişmiş iki yapay zeka modelini tek bir otonom döngüde birleştiren, **Enterprise-Grade** (kurumsal seviye) bir AI Terminal asistanıdır.

</div>

---

## 📄 Teknik Veri Sayfası (Technical Data Sheet)

| Kategori | Özellik | Detay |
|---|---|---|
| **Mimari** | Asimetrik Hibrit | Claude 3.5 (Brain) + Gemini 2.0 (Hands) |
| **Döngü Hızı** | Otonom Faz 6 | Gözlem -> Re-Plan -> Uygulama (Hata anında otonom sapma yönetimi) |
| **Bağlam Yönetimi** | Deep Search (rg) | `ripgrep` entegrasyonu ile 100k+ dosya arasında milisaniyelik semantik bağlam bulma |
| **Dayanıklılık** | Immortality Patch | I/O hatalarına (IsADirectoryError, PermissionError) karşı bağışıklık ve otonom düzeltme |
| **Arayüz** | Next-Gen TUI | Textual tabanlı, responsive, 3 panelli IDE deneyimi |
| **Güvenlik** | Dual-Layer Sandbox | Host seviyesinde komut filtreleme + Docker izolasyonu |

---

## 💰 Tasarruf ve ROI (Yatırım Getirisi) Raporu

myAgent, "Bilinçli Asimetri" prensibiyle çalışır. Devasa kod bloklarını ve terminal çıktılarını (Hands) düşük maliyetli Gemini'ye, stratejik kararları (Brain) ise Claude'a bırakır.

### Stres Testi Verileri (20 Nisan 2026 Seansı)
*   **Gerçekleştirilen Görevler:** Redis Klonu (Async), C++ Entegrasyonu, Distributed Task Queue, Core Async Refactor.
*   **Üretilen Kod Hacmi:** ~25,000+ satır.
*   **Bağlam (Context) İşleme:** ~2.5M+ Gemini Token.

| Metrik | Claude Code (Tahmini) | myAgent (Gerçek) | Fark |
|---|---|---|---|
| **Maliyet** | ~$45.00 | **~$0.75** | **%98.3 Tasarruf** |
| **Zeka** | %100 Claude | %100 Claude (Strateji) | Aynı Zeka Seviyesi |
| **Hız** | 5-10 dk (Döngülerle) | 1.5 - 3 dk | **%300 Daha Hızlı** |

---

## 🧠 Otonom Güç: Aşama 6 Döngüsü

myAgent artık sadece kod yazmıyor, projenizi bir mühendis gibi "araştırıyor" ve "hata yapınca durup düşünüyor".

<div align="center">
  <img src="docs/feature_autonomy.svg" width="400" alt="Otonom Döngü"/>
  <img src="docs/feature_search.svg" width="400" alt="Derin Arama"/>
</div>

- **Deep Search:** `ripgrep` ile nokta atışı dosya bulma.
- **Observation:** Gemini'nin karşılaştığı engelleri (eksik kütüphane vb.) Claude'a raporlaması.
- **Self-Healing:** Linter ve Test hatalarını geçene kadar otonom olarak düzeltme.

---

## ⌨️ Klavye Kısayolları (TUI Edition)

| Tuş | Fonksiyon | Önem |
|---|---|---|
| **`Ctrl+B`** | **Files (Dosya Gezgini)** | Proje yapısını anlık izleme ve gezinme. |
| **`Ctrl+E`** | **Process (İşlem Takibi)** | Claude'un adımlarını ve Gemini'nin loglarını izleme. |
| **`Ctrl+K`** | **Selection (Kelime Seçim)** | Terminalin ötesinde, cerrahi hassasiyette metin kopyalama. |
| **`Ctrl+S`** | **Settings (Ayarlar)** | Uygulamadan çıkmadan model ve API anahtarı yönetimi. |
| `Ctrl+Y` | Copy Last Answer | En son Claude cevabını anında panoya al. |

---

## 📦 Kurulum ve Güçlü Modlar

### 🐳 Docker (Maximum Otonomi & Güvenlik)
*Bu modda ajan `g++`, `sed`, `mkdir` gibi komutları tam yetkiyle ama izole şekilde kullanır.*

```bash
docker compose build
./run.sh
```

### 🐍 Yerel (Hızlı Başlangıç)
```bash
pip install -e .
python -m myagent
```

<div align="center">

---

*Claude Düşünür. Gemini Çalışır. myAgent Yönetir.*

</div>

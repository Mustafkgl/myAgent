
```
                      ___                    __
     ____ ___  __  __/   | ____ ____  ____  / /_
    / __ `__ \/ / / / /| |/ __ `/ _ \/ __ \/ __/
   / / / / / / /_/ / ___ / /_/ /  __/ / / / /_
  /_/ /_/ /_/\__, /_/  |_\__, /\___/_/ /_/\__/
            /____/      /____/
```

<div align="center">

**Claude düşünür. Gemini çalışır. Sen sadece ne istediğini söylersin.**

*Terminal tabanlı çift-model AI ajanı — planlama, yürütme, review, hafıza*

</div>

---

## Fikir

Çoğu AI ajanı aynı modeli tekrar tekrar çağırır. myAgent farklı bir yaklaşım benimser: **bilinçli asimetri.**

```
Kullanıcı girişi
       │
       ▼
  Claude (Planner)          ← akıllı, pahalı — sadece yönetir
  "3 adımda yap..."
       │
       ▼
  Gemini (Worker)           ← hızlı, ücretsiz — tüm ağır işi yapar
  FILE: main.py ...
  BASH: pytest ...
       │
       ▼
  Claude (Reviewer)         ← kodu inceler, hataları yakalar
  "LGTM / Şunu düzelt..."
       │
       ▼
  Claude (Verifier)         ← eksik bir şey var mı kontrol eder
  "COMPLETE"
       │
       ▼
  Sonuç — /workspace
```

**Neden önemli:** Claude Code ile aynı işi yaparken Claude token harcamanın onda birine çalışırsın. Pahalı modeli sadece beyne ver, bedava modeli kola.

---

## Özellikler

- **TUI modu** — tam ekran Textual arayüzü, `/` ile komut otomatik tamamlama
- **REPL modu** — klasik terminal, aynı güç
- **Çift model pipeline** — Claude planlar+inceler, Gemini yürütür
- **Konuşma hafızası** — "bunu düzelt", "test ekle" gibi doğal referanslar çalışır
- **Session kalıcılığı** — oturumlar JSON'a kaydedilir, isimlendirilir, geri yüklenir
- **Canlı yeniden boyutlandırma** — terminal resize olunca içerik anında reflow olur
- **Auth esnekliği** — API key veya OAuth (Claude Code / Gemini CLI)
- **Güvenli yürütme** — path traversal koruması, `shell=False` zorunluluğu

---

## Kurulum

### Gereksinimler

| Gereksinim | Açıklama |
|---|---|
| Python 3.10+ | |
| **Claude için** | `ANTHROPIC_API_KEY` **veya** Claude Code CLI (`claude login`) |
| **Gemini için** | `GEMINI_API_KEY` **veya** Gemini CLI (`gemini login`) |

> Claude Code CLI kullanıyorsan API key'e gerek yok. Aboneliğin (Pro/Max) doğrudan kullanılır.

### Seçenek A — Python venv

```bash
git clone https://github.com/Mustafkgl/myAgent.git
cd myAgent/myagent

# uv (önerilir, daha hızlı)
uv venv .venv && source .venv/bin/activate
uv pip install -e .

# ya da standart pip
python -m venv .venv && source .venv/bin/activate
pip install -e .

# başlat
python -m myagent --tui          # TUI modu
python -m myagent                # REPL modu
```

### Seçenek B — Docker (önerilir)

Docker ile `~/.claude`, `~/.gemini`, `~/.myagent` klasörleri otomatik mount edilir — hiçbir şeyi elle yapılandırmak zorunda değilsin.

```bash
cd myAgent/myagent

docker compose build             # image oluştur
docker compose run --rm myagent  # başlat
```

Kısayol script:

```bash
./run.sh                         # interaktif REPL
./run.sh "port scanner yaz"      # tek seferlik görev
./run.sh --build                 # rebuild + başlat
./run.sh --shell                 # container bash'ine gir
```

### İlk Çalıştırma

İlk çalıştırmada kurulum sihirbazı başlar. Hangi auth modunu ve hangi modelleri kullanacağını sorar. Sonradan `myagent --setup` ile veya TUI içinden `/auth` ve `/model` ile değiştirilebilir.

---

## TUI Modu

```bash
python -m myagent --tui
```

```
                      ___                    __
     ____ ___  __  __/   | ____ ____  ____  / /_
    / __ `__ \/ / / / /| |/ __ `/ _ \/ __ \/ __/
   / / / / / / /_/ / ___ / /_/ /  __/ / / / /_
  /_/ /_/ /_/\__, /_/  |_\__, /\___/_/ /_/\__/
            /____/      /____/

  v1.0.0  ·  Claude planlar  ·  Gemini yürütür

  claude-sonnet-4-6  /  gemini-2.5-flash

  ↑↓ geçmiş · Tab otomatik tamamla · Ctrl+Y kopyala · Ctrl+L temizle · F1 yardım

 ❯  Ne yapmamı istersin?
```

### Klavye Kısayolları

| Kısayol | Açıklama |
|---|---|
| `↑` / `↓` | Girdi geçmişinde gez |
| `Tab` | Slash komutunu otomatik tamamla |
| `Ctrl+Y` | Son AI cevabını panoya kopyala |
| `Ctrl+L` | Ekranı temizle |
| `F1` | Yardım |
| `Ctrl+C` | İlk basış uyarı verir, ikinci basış çıkış |
| `Esc` | Auth/Model ekranlarını kapat |

### Slash Komutları

`/` yazmaya başlayınca altta otomatik tamamlama listesi açılır. `↑` `↓` ile seç, `Tab` veya `Enter` ile tamamla.

| Komut | Açıklama |
|---|---|
| `/help` | Tüm komutları ve kısayolları göster |
| `/auth` | Kimlik doğrulama ekranı — API key veya OAuth ayarla |
| `/model` | Model seçim ekranı — Claude ve Gemini modellerini değiştir |
| `/config` | Mevcut yapılandırmayı göster |
| `/status` | Oturum istatistikleri |
| `/about` | Versiyon ve model bilgileri |
| `/think` | Verbose (ayrıntılı çıktı) modunu aç/kapat |
| `/theme dark\|light` | Temayı değiştir |
| `/sessions` | Kayıtlı oturumları listele |
| `/load <n>` | Oturum yükle — numara veya ID ile |
| `/rename <ad>` | Mevcut oturumu yeniden adlandır |
| `/new` | Yeni oturum başlat |
| `/export` | Oturumu `~/myagent_export_*.md` dosyasına aktar |
| `/compact` | Konuşma geçmişini Claude ile özetleyip sıkıştır |
| `/editor` | `$EDITOR` açılır, çok satırlı giriş yap |
| `/clear` | Ekranı temizle |
| `/exit` | Uygulamadan çık |

### /auth Ekranı

```
PLANLAYAN  —  Claude  ( ↑ ↓ ile seç )
  Aboneliğinle kullan (Claude Code) ya da API key gir

  ○ API Anahtarı       ~3 s/plan  · pay-as-you-go
  ● Claude Code CLI    ~5 s/plan  · abonelik (Pro/Max)

  ✓ Claude Code kurulu ve giriş yapılmış

──────────────────────────────────────────────

ÇALIŞAN  —  Worker  ( ↑ ↓ ile seç · Tab ile bu bölüme geç )
  Görevleri kimin yürüteceğini seç

  ● Gemini API         ~2 s/adım  · hızlı, GEMINI_API_KEY gerekli
  ○ Claude Code        ~5 s/adım  · aynı aboneliği kullanır
  ○ Gemini CLI         ~40 s/adım · yavaş, Node.js CLI

  [  Kaydet ve Devam Et  ]
```

- **Claude Code CLI seçiliyse** ve giriş yapılmamışsa `claude login` butonu çıkar, terminal suspend olup tarayıcıya yönlendirir
- **API Key seçiliyse** şifreli giriş alanı açılır, kaydedilen key `~/.myagent/.env`'e yazılır

### /model Ekranı

API key varsa canlı model listesi çekilir, yoksa curated liste gösterilir.

```
PLANLAYAN  —  Claude  ( ↑ ↓ ile seç )

  ● claude-opus-4-6  ★  (mevcut)  —  Most capable, complex planning
  ○ claude-sonnet-4-6              —  Balanced speed and quality
  ○ claude-haiku-4-5-...           —  Fast and lightweight

──────────────────────────────────────────────

ÇALIŞAN  —  Gemini  ( ↑ ↓ ile seç · Tab ile bu bölüme geç )

  ● gemini-2.5-flash  ★  (mevcut)  —  Fast with built-in reasoning
  ○ gemini-2.5-pro                  —  Most capable, complex tasks
  ○ gemini-2.0-flash                —  Stable fallback

  [  Kaydet ve Devam Et  ]
```

`★` önerilen modeli gösterir. `(mevcut)` aktif seçimi işaretler.

---

## REPL Modu

```bash
python -m myagent
```

Her türlü girdi kabul edilir. Claude, soruyu yanıtlayacak mı yoksa pipeline'ı başlatacak mı kendisi karar verir.

```
myagent> basit bir şifre üreteci yaz
myagent> buna GUI ekle
myagent> az önce yazdığın kodu açıkla
myagent> fibonacci nedir?
myagent> düzelt
myagent> test ekle
```

### REPL Komutları

| Komut | Açıklama |
|---|---|
| `<herhangi bir şey>` | Claude yönlendirir: soru mu, görev mi? |
| `run <görev>` | Chat'i atlayıp doğrudan pipeline'a gönder |
| `devam` / `devam et` | Son projeye kaldığın yerden devam et |
| `düzelt` / `fix` | Son projede hataları düzelt |
| `test ekle` | Son projeye testler ekle |
| `geçmiş` / `history` | Tüm geçmiş görevleri göster |
| `son` / `last` | Son görevin detayları |
| `dosyalar` / `ls` | Workspace'deki dosyaları listele |
| `temizle` | Workspace'i temizle |
| `setup` | Auth ve model ayarlarını yeniden yapılandır |
| `models` | Mevcut modelleri listele |
| `config` | Yapılandırmayı göster |
| `help` | Yardım |
| `exit` | Çıkış |

---

## Tek Seferlik (One-shot) Mod

```bash
# Temel kullanım
python -m myagent "REST API yaz, endpoint'leri test et"

# Model seçimi
python -m myagent "veri analizi yap" --claude-model sonnet --gemini-model 2.5-pro

# Sadece planı gör, çalıştırma
python -m myagent "web scraper yaz" --dry-run

# Ayrıntılı çıktı
python -m myagent "şifreleme kütüphanesi yaz" --verbose

# Görev öncesi netleştirme soruları
python -m myagent "büyük proje başlat" --clarify

# Farklı çalışma dizini
python -m myagent "dosya dönüştürücü yaz" --work-dir ~/projeler/converter
```

---

## Tüm CLI Seçenekleri

```
python -m myagent [GÖREV] [SEÇENEKLER]
```

| Seçenek | Açıklama |
|---|---|
| `--tui` | Textual TUI modunda başlat |
| `--claude-model MODEL` | Claude modeli — alias veya tam ID |
| `--gemini-model MODEL` | Gemini modeli — alias veya tam ID |
| `--claude-mode api\|cli` | Claude auth modunu geçersiz kıl |
| `--gemini-mode api\|cli` | Gemini auth modunu geçersiz kıl |
| `--work-dir PATH` | Dosya yazma dizini |
| `--max-steps N` | Maksimum plan adımı (varsayılan: 10) |
| `--dry-run` | Planı göster, yürütme |
| `--sequential` | Adımları sırayla yürüt |
| `--no-review` | Review döngüsünü atla |
| `--no-complete` | Completion verification'ı atla |
| `--max-review-rounds N` | Maksimum review turu (varsayılan: 2) |
| `--clarify` | Başlamadan önce netleştirme soruları sor |
| `--auto-deps` | Eksik pip paketlerini otomatik kur |
| `--lang tr\|en` | Çıktı dilini zorla |
| `--verbose` / `-v` | Ham model çıktısını göster |
| `--list-models` | Mevcut modelleri listele ve çık |
| `--config` | Yapılandırmayı göster ve çık |
| `--setup` | Kurulum sihirbazını çalıştır |
| `--version` | Versiyon bilgisi |

### Model Alias'ları

**Claude:**

| Alias | Model ID |
|---|---|
| `opus` | `claude-opus-4-6` |
| `sonnet` | `claude-sonnet-4-6` |
| `haiku` | `claude-haiku-4-5-20251001` |

**Gemini:**

| Alias | Model ID |
|---|---|
| `2.5-flash` | `gemini-2.5-flash` |
| `2.5-pro` | `gemini-2.5-pro` |
| `flash` | `gemini-2.0-flash` |

---

## Pipeline — Detaylı Akış

### 1. Chat Katmanı

Her girdi önce Chat modülüne gelir. Claude kısa bir değerlendirme yapar:

- **Soru / açıklama** → Markdown yanıt döner, konuşma geçmişi korunur
- **Görev** → İngilizce task tanımına çevrilir, pipeline başlatılır

Konuşma geçmişi session boyunca tutulur (son 10 tur). "bunu düzelt", "buna test ekle" gibi referanslar doğal çalışır.

### 2. Planner

Claude görevi 3–10 atomik adıma böler. Workspace'deki mevcut dosyaları, AST sembol haritasını ve görev geçmişini de görür — var olan kodu yeniden yazmaz.

```
STEP 1: Create calculator.py with add(), subtract(), multiply(), divide()
STEP 2: Write test_calculator.py with pytest assertions for all functions
STEP 3: Run pytest to verify all tests pass
```

### 3. Worker

Tüm adımlar tek bir toplu çağrıda Gemini'ye gönderilir. Her adım `===END===` ayracıyla ayrılmış `FILE:` veya `BASH:` bloğu döner.

```
FILE: calculator.py
def add(a, b):
    return a + b
...
===END===
FILE: test_calculator.py
import pytest
from calculator import add
...
===END===
BASH: python -m pytest test_calculator.py -v
===END===
```

### 4. Review Döngüsü

Dosyalar yazıldıktan sonra Claude kodu inceler:

1. `ruff` lint kontrolü (`--fix` otomatik uygulanır)
2. `pytest` varsa testleri çalıştırır
3. Hata varsa → Gemini'ye düzeltme adımları gönderir
4. Başarıya kadar tekrar — maksimum 2 tur

### 5. Completion Verification

Claude oluşturulan dosyaları okur ve asıl görevle karşılaştırır:

- `COMPLETE` → bitti
- `INCOMPLETE: STEP 1: ...` → Gemini'ye eksik adımlar gönderilir, tekrar doğrulanır

### 6. Kalıcı Hafıza

Her görev `~/.myagent/history.jsonl`'e kaydedilir. Bir sonraki görevde Claude bu geçmişi görür:

```
Past tasks:
1. [2026-04-15] "fibonacci web app" → fibonacci.py, app.py, index.html
2. [2026-04-16] "calculator with tests" → calculator.py, test_calculator.py
```

---

## Auth Yapılandırması

### Desteklenen Modlar

| Sağlayıcı | Mod | Gereksinim |
|---|---|---|
| Claude | `api` | `ANTHROPIC_API_KEY` |
| Claude | `cli` | `claude` CLI + `claude login` |
| Gemini | `api` | `GEMINI_API_KEY` |
| Gemini | `cli` | `gemini` CLI + `gemini login` |
| Worker | `claude` | Claude CLI (worker olarak da kullanır) |

### Önerilen Yapılandırma (API key gerekmez)

```json
{
  "claude_mode": "cli",
  "claude_model": "claude-sonnet-4-6",
  "gemini_mode": "cli",
  "gemini_model": "gemini-2.5-flash"
}
```

`~/.myagent/config.json` dosyasına kaydedilir veya TUI içinden `/auth` ile ayarlanır.

### API Key ile Yapılandırma

```bash
# ortam değişkenleri (geçici)
export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=AIza...

# ya da TUI'den /auth → API Anahtarı seç → yapıştır → Kaydet
# ~/.myagent/.env dosyasına kalıcı olarak yazılır
```

### Claude Code CLI (OAuth, abonelik)

Claude Code kuruluysa ve `claude login` yapılmışsa, API key'e gerek yoktur. myAgent bu oturumu kullanır.

```bash
# Claude Code kurulu değilse
curl -fsSL https://claude.ai/install.sh | sh
claude login     # tarayıcı açılır, abonelik hesabınla giriş yap

# myAgent'ta /auth → Claude Code CLI seç → Kaydet
```

---

## Güvenlik

### Path Traversal Koruması

Tüm dosya yazma işlemlerinde hedef yol `WORK_DIR` altında kontrol edilir:

```python
target = (WORK_DIR / filename).resolve()
target.relative_to(WORK_DIR.resolve())  # ValueError → reddedilir
```

`../../etc/passwd` ve benzeri tüm girişimler sessizce reddedilir.

### Komut Yürütme

- `shell=False` — her komut `shlex.split()` ile liste olarak çalışır
- `eval()` ve `exec()` hiçbir yerde kullanılmaz
- Docker dışında izin listesi: `mkdir`, `touch`, `echo`, `cat`
- Docker içinde (`MYAGENT_DOCKER=1`) container sandbox yeterli

---

## Proje Yapısı

```
myagent/
├── myagent/
│   ├── cli.py              — REPL, argparse, SessionState
│   ├── tui.py              — Textual TUI, slash komutları, session yönetimi
│   ├── auth_screen.py      — /auth ekranı (Textual Screen)
│   ├── model_screen.py     — /model ekranı (Textual Screen)
│   ├── ui.py               — Rich terminal UI (streaming, paneller, Live)
│   ├── interrupt.py        — ESC / Ctrl+C yönetimi
│   ├── models.py           — model kayıt defteri, alias çözümü, canlı keşif
│   ├── setup_wizard.py     — ilk çalıştırma sihirbazı
│   │
│   ├── agent/
│   │   ├── chat.py         — soru ↔ görev routing, konuşma geçmişi
│   │   ├── planner.py      — Claude → STEP listesi
│   │   ├── worker.py       — Gemini → FILE/BASH toplu çıktısı
│   │   ├── executor.py     — dosya yazımı + güvenli komut yürütme
│   │   ├── reviewer.py     — ruff + pytest + Claude düzeltme döngüsü
│   │   ├── completer.py    — Claude tamamlama doğrulayıcı
│   │   ├── clarifier.py    — görev öncesi netleştirme soruları
│   │   ├── deps.py         — eksik pip paket tespiti ve kurulumu
│   │   └── pipeline.py     — tam döngü orkestrasyonu
│   │
│   ├── memory/
│   │   └── history.py      — kalıcı görev geçmişi (jsonl + dosya indeksi)
│   │
│   ├── i18n/
│   │   ├── translator.py   — TR↔EN sözlük (API çağrısı yok)
│   │   └── locale.py       — sistem dili tespiti
│   │
│   ├── prompts/
│   │   ├── planner.txt
│   │   ├── worker.txt
│   │   ├── worker_batch.txt
│   │   └── clarifier.txt
│   │
│   └── config/
│       ├── settings.py     — sabitler, validate()
│       └── auth.py         — mod/model tespiti, override, config I/O
│
├── docker-compose.yml
├── Dockerfile
└── run.sh
```

---

## Yapılandırma Dosyaları

| Dosya | İçerik |
|---|---|
| `~/.myagent/config.json` | Mod ve model tercihleri |
| `~/.myagent/.env` | API key'ler (TUI'den kaydedilince oluşur) |
| `~/.myagent/sessions/*.json` | TUI oturum geçmişi |
| `~/.myagent/history.jsonl` | Görev geçmişi |

### Ortam Değişkenleri

| Değişken | Açıklama |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API anahtarı |
| `GEMINI_API_KEY` | Gemini API anahtarı |
| `MYAGENT_WORK_DIR` | Dosya yazma dizini (varsayılan: `./workspace`) |
| `MYAGENT_DOCKER` | `1` ise komut whitelist devre dışı |
| `MYAGENT_CLAUDE_MODE` | `api` veya `cli` — config'i geçersiz kılar |
| `MYAGENT_GEMINI_MODE` | `api` veya `cli` — config'i geçersiz kılar |

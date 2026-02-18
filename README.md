# 📦 Resourcepack-Converter

Konversi resource pack Minecraft Java Edition agar support **1.20.1 hingga 1.21.10** dalam **1 file zip** menggunakan sistem overlay.

Support: **ItemsAdder** · **Nexo** · **ModelEngine v3/v4** · **Vanilla**

Klik tombol di bawah ini untuk langsung convert pack kamu:

[![🚀 CONVERT PACK SEKARANG](https://img.shields.io/badge/🚀_CONVERT_PACK_SEKARANG-2ea44f?style=for-the-badge)](../../issues/new?template=convert_request.yml)

> Tombol di atas akan membuka halaman form. Isi URL pack dan versi asli, lalu submit.

---

## Langkah-langkah Detail

**1.** Klik tombol **CONVERT PACK SEKARANG** di atas

**2.** Isi form:
- **URL Resource Pack** — link download pack kamu (Dropbox, GDrive, MediaFire, dll)
- **Nama Output** — nama file hasil (opsional)
- **Tipe Pack** — pilih ItemsAdder / Nexo / ModelEngine / Vanilla
- **Versi Asli** — versi Minecraft pack tersebut dibuat

**3.** Klik **Submit new issue**

**4.** Tunggu beberapa menit. Bot akan otomatis memproses dan membalas di issue kamu dengan link download

**5.** Download hasil dari bagian **Artifacts** di link yang dikirim bot

---

## Format Link yang Didukung

| Platform | Contoh |
|----------|--------|
| Dropbox | `https://www.dropbox.com/s/xxx/pack.zip?dl=0` → otomatis jadi `dl=1` |
| Google Drive | `https://drive.google.com/file/d/xxx/view` |
| MediaFire | `https://www.mediafire.com/file/xxx` |
| OneDrive | `https://1drv.ms/u/xxx` |
| MCPacks | `https://mcpacks.net/p/xxx` |
| GitHub Release | `https://github.com/user/repo/releases/download/v1/pack.zip` |

> Link akan **otomatis dikonversi** ke direct download. Tidak perlu ubah manual.

---

## Versi yang Didukung

| Overlay | Versi Minecraft | Pack Format |
|---------|----------------|-------------|
| Root (base) | Mengikuti versi pack asli | — |
| overlay_v1_21_4 | 1.21.4 – 1.21.10 | 46–57 |
| overlay_v1_21_2 | 1.21.2 – 1.21.3 | 42–45 |
| overlay_v1_20_5 | 1.20.5 – 1.21.1 | 32–41 |
| overlay_v1_20_2 | 1.20.2 – 1.20.4 | 18–31 |
| overlay_v1_20_1 | 1.20.1 | 15–17 |

### ⚠️ Catatan OptiFine CIT

Jika pack menggunakan **OptiFine CIT** (Custom Item Textures), converter akan **otomatis skip** konversi ke format `item.json` baru. Pack akan tetap menggunakan format lama (`model.json` dengan `overrides`) untuk kompatibilitas dengan OptiFine di semua versi 1.20.1–1.21.10.

**Ciri pack pakai OptiFine CIT:**
- Ada folder `optifine/cit/` dengan file `.properties`
- Biasanya digunakan untuk ItemsAdder armor dengan custom textures

**Kenapa skip?**  
OptiFine di 1.21.4 belum support format `item.json` baru dan akan stuck di "Waiting for model sprites".

---

## Cara Pakai Manual (Via GitHub Actions)

Jika kamu familiar dengan GitHub Actions:

1. Pergi ke tab **Actions**
2. Pilih **Konversi Resource Pack**
3. Klik **Run workflow**
4. Masukkan URL pack dan nama output
5. Download hasil dari **Artifacts**

---

## Untuk Developer

### Struktur Folder

```
Resourcepack-Converter/
├── scripts/
│   ├── manager.py          # Orchestrator utama
│   ├── detector.py         # Deteksi tipe pack & versi
│   ├── link_converter.py   # Konversi link ke direct download
│   ├── item_converter.py   # Konversi item model → item.json (1.21.2+)
│   ├── overlay_builder.py  # Build struktur overlay
│   └── modelengine.py      # Handler ModelEngine v3/v4
├── .github/
│   ├── workflows/
│   │   └── convert.yml
│   └── ISSUE_TEMPLATE/
│       └── convert_request.yml
├── LICENSE
└── README.md
```

### Jalankan Lokal

```bash
cd scripts
python manager.py --url "https://dropbox.com/s/xxx/pack.zip?dl=0" --output my_pack
```

---

## License

[MIT](LICENSE) © 2026 MortazDev

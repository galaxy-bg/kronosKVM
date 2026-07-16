# KronosKVM

Raspberry Pi Compute Module 4 üzerinde çalışan, PiKVM yaklaşımından esinlenen
açık kaynak IP-KVM yazılımı.

> Proje erken geliştirme aşamasındadır. Henüz gerçek bir makineyi güvenli
> şekilde yönetmek için hazır değildir.

## Hedef mimari

- Raspberry Pi OS Lite 64-bit (Debian Bookworm/Trixie)
- Python 3.11+
- `aiohttp` tabanlı asenkron yönetim API'si
- HDMI video yakalama için ayrı yayın servisi
- USB HID ve sanal disk için Linux USB Gadget
- ATX güç kontrolü için izole GPIO donanım katmanı
- `systemd` ile servis yönetimi

PiKVM önemli bir teknik referanstır, ancak KronosKVM bağımsız geliştirilecektir.
PiKVM kodu veya varlıkları doğrudan bu depoya alınmayacaktır.

## Yerel geliştirme

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp config/kronoskvm.example.toml config/kronoskvm.toml
kronoskvm
```

Servis varsayılan olarak `http://127.0.0.1:8080` adresinde açılır:

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/v1/system
```

Test ve kalite kontrolleri:

```bash
pytest
ruff check .
```

## CM4 kurulumu

Raspberry Pi üzerinde sanal ortam kullanılır; Raspberry Pi OS'un sistem
Python kurulumuna doğrudan `pip` paketi yüklenmez.

```bash
sudo ./scripts/install.sh
```

Kurulum betiği uygulamayı `/opt/kronoskvm` altına kurar, örnek ayarı
`/etc/kronoskvm/config.toml` konumuna yerleştirir ve `systemd` servisini
etkinleştirir.

## Yol haritası

- [x] Yönetim API'si ve sistem sağlık bilgisi
- [ ] Kimlik doğrulama ve HTTPS
- [ ] HDMI yakalama ve düşük gecikmeli video
- [ ] USB klavye/fare emülasyonu
- [ ] Sanal CD/USB depolama
- [ ] İzole ATX güç kontrolü
- [ ] Salt okunur kök dosya sistemi ve güvenli güncelleme

## Lisans

Henüz lisans seçilmedi. Bir lisans eklenene kadar tüm hakları saklıdır.

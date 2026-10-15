# KDX InfraBox — WireGuard kurulum ve kayıt kılavuzu

Bu kılavuz, yeni bir WireGuard sunucusu hazırlamayı, çalışan bir InfraBox'ı manuel
veya otomatik kaydetmeyi ve IP/endpoint ayarlarını değiştirmeyi anlatır. Raspberry
Pi OS, donanım ve temel InfraBox kurulumu için önce [ana kurulum](../README.md#appliance-installation)
adımlarını tamamlayın. Buradaki sunucu kurulumunu mevcut çalışan `wg0` üzerine
uygulamayın; o durumda doğrudan script kurulumuna geçin.

İşlemler yönetici tarafından yürütülür. Parolaları, private key'leri, özel cihaz
konfigürasyonunu ve root-only yedekleri GitHub'a koymayın. Komutlarda örnek
adresleri kendi ağınıza göre değiştirin. Bu kılavuz canlı cihazlarda kendiliğinden
herhangi bir değişiklik yapmaz.

## 1. Adresleri birbirinden ayırın

| Ayar | Örnek | Nerede kullanılır? |
| --- | --- | --- |
| Sunucu yönetim IP/DNS | `172.20.2.74` | Yönetici SSH erişimi ve kayıt scripti |
| Sunucu dış endpoint'i | `vpn.example.com:51820` | Infrabox'ın WireGuard bağlantısı |
| Sunucu tünel IP'si | `10.77.0.1/24` | `wg0` arayüzü |
| Infrabox Ethernet IP'si | `192.168.31.26` | Yerel GUI/SSH; VPN IP'sinden bağımsız |
| Infrabox VPN IP'si | `10.77.0.11/32` | VPN üzerinden cihaz yönetimi |
| Varsayılan dağıtım havuzu | `10.77.0.11`–`10.77.0.254` | Yeni cihazlara adres tahsisi |
| İzin verilen VPN rotası | `10.77.0.0/24` | Sadece VPN ağı; internet varsayılan rotası değişmez |
| Yönetim Wi-Fi ağı | `192.168.34.0/24` | Yerel kurtarma; VPN ile çakışmamalı |

**Yönetim IP'sini dış endpoint sanmayın.** Yönetici bilgisayarınız kurumsal VPN
üzerinden sunucuya erişirken InfraBox aynı adrese erişemeyebilir. Dış IP yerine
kuruluşunuzun kontrolündeki bir DNS adı kullanmak adres değişikliğini kolaylaştırır.

Varsayılan mimari:

```text
Infrabox Ethernet / USB WAN
  ├── kayıt: doğrulanmış SSH → süreli yetki → sunucu scripti
  └── VPN: vpn.example.com:51820/UDP → Forti VIP → wg0 → 10.77.0.1

Infrabox Web GUI: Settings → WireGuard VPN
  ├── Generate & Register
  ├── manuel kimlik / public kayıt isteği / kayıt yanıtı
  └── Connect / Disconnect / Restart / automatic startup
```

## 2. Yeni Rocky Linux 9 sunucusunu hazırlayın

Bu bölüm yalnızca **yeni, üzerinde `wg0` bulunmayan sunucu** içindir.

```bash
sudo dnf install -y wireguard-tools python3
sudo modprobe wireguard
sudo install -d -m 0700 /etc/wireguard
```

Sunucu anahtarını bellekte üretip root-only konfigürasyona yazın. Aşağıdaki komut
var olan `wg0.conf` dosyasını değiştirmez; dosya varsa hata verir. Private key
terminale basılmaz:

```bash
sudo python3 - <<'PY'
import os
import subprocess

private = subprocess.run(
    ['wg', 'genkey'], capture_output=True, text=True, check=True,
).stdout.strip()
fd = os.open('/etc/wireguard/wg0.conf', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write('[Interface]\n')
    stream.write('Address = 10.77.0.1/24\n')
    stream.write('ListenPort = 51820\n')
    stream.write('PrivateKey = ' + private + '\n')
    stream.write('SaveConfig = false\n')
PY
sudo systemctl enable --now wg-quick@wg0
sudo wg show wg0 public-key
sudo wg show wg0 listen-port
ip -brief address show wg0
```

Son iki `wg` komutu public key ve portu gösterir. `wg showconf` veya `wg ... dump`
çıktısını paylaşmayın; private bilgiler içerebilir.

Firewalld kullanılıyorsa önce sunucunun dış arayüzünün hangi zone'da olduğunu bulun:

```bash
sudo firewall-cmd --get-active-zones
```

Örneğin doğru zone `public` ise yalnızca gereken WireGuard UDP portunu açın:

```bash
sudo firewall-cmd --zone=public --add-port=51820/udp
sudo firewall-cmd --permanent --zone=public --add-port=51820/udp
```

Bu kurulum için müşteri LAN forwarding, masquerade veya default-route değişikliği
gerekmez. Bunları otomatik eklemeyin. Sunucu üzerinde mevcut firewall yönetimini
koruyun; firewalld kullanılmıyorsa sırf bu örnek için devreye almayın.

### Forti / NAT arkasındaki sunucu

Forti tarafında dış endpoint'in UDP portunu sunucuya yönlendirin:

```text
vpn.example.com:51820/UDP → SUNUCU_YONETIM_IP:51820/UDP
```

VIP/DNAT tanımıyla eşleşen WAN→sunucu firewall policy'si de gerekir. Dış port ile
sunucunun dinlediği iç port farklı olabilir; **cihaza dış portu** verin. Var olan
kuralları ve kısıtları koruyun. SSH'nin internete açılması zorunlu değildir;
otomatik kayıt için aşağıdaki geçici yönetim tüneli kullanılabilir.

## 3. Sunucu scriptlerini kurun

GitHub'daki bu branch/sürümün kaynak kodunu yönetici bilgisayarına veya sunucuya
alın. Repo URL'si: `https://github.com/galaxy-bg/kronosKVM`.

```bash
sudo install -m 0755 scripts/kdx-wg-server.sh /usr/local/sbin/
sudo install -m 0755 scripts/kdx-wg-server.py /usr/local/sbin/
sudo install -m 0755 scripts/kdx-wg-enroll.py /usr/local/sbin/
sudo /usr/local/sbin/kdx-wg-server.sh status
```

Üç dosyayı birlikte ve aynı dizine koyun. Python dosyaları repo backend paketine
bağımlı değildir; Python standard library ve kurulu `wg` kullanırlar.

| Dosya | Görevi |
| --- | --- |
| `kdx-wg-server.sh` | Yönetim komutlarının giriş noktası |
| `kdx-wg-server.py` | IP tahsisi, peer ekleme/silme, yedek ve rollback |
| `kdx-wg-enroll.py` | Süreli SSH kayıt yetkisi verme, kayıt isteğini işleme, yetki iptali |

Mevcut peer'lar korunur. Değişiklik yalnızca ilgili peer'a uygulanır; `wg0`
yeniden başlatılmaz. `SaveConfig=true` varsa araç değişikliği reddeder. Önce
canlı/disk konfigürasyonunu yerelde yedekleyip uzlaştırın ve onaylı bakım işlemiyle
`SaveConfig=false` yapın; çalışan sunucuyu körlemesine yeniden başlatmayın.

## 4. Infrabox tarafını hazırlayın

Çalışan temel InfraBox kurulumuna, bu sürümün `backend`, `frontend`, `scripts` ve
`deploy` dosyalarını standart proje dağıtımıyla yükleyin. Özel cihaz ayarlarını,
`.env`, TLS ve `/var/lib/kronoskvm/state` içeriğini başka kutudan kopyalamayın.

Güncellemeden önce uygulama, özel konfigürasyon ve mevcut image tag'lerini root-only
yedekleyin. Sonra cihazda:

```bash
cd /opt/kronoskvm
sudo bash scripts/install-wireguard-provisioning.sh
sudo docker-compose build api web
sudo systemctl reload kronoskvm-containers.service
```

Container servisi inactive ise `reload` yerine `start` kullanın. Yeni cihazda
servisin açılışta çalışması temel kurulumun parçasıdır. Eski kurulumun servisini
ve Docker sürümüne uygun mevcut Compose komutunu kullanın.

**Infrabox'ta `wg-kdx` sahibi NetworkManager'dır.** `wg-quick@wg-kdx` servisini
ayrıca etkinleştirmeyin. `/etc/wireguard/wg-kdx.conf` kurtarma kopyasıdır;
bağlantıyı mevcut systemd host kontrolcüsü yönetir.

| Dosya (`/opt/kronoskvm/scripts/`) | Görevi |
| --- | --- |
| `install-wireguard-provisioning.sh` | WireGuard araçları ve mevcut systemd entegrasyonu |
| `infrabox-wireguard.py` | Kimlik, kayıt, bağlantı ve açılış tercihinin CLI'si |
| `remote-assist-host.py` | GUI kuyruğunu işleyen root kontrolcü |
| `configure-auto-enrollment.py` | Kısıtlı SSH transport anahtarı ve onaylı kayıt yetkisi |

GUI: **`https://INFRABOX_IP` → Settings → WireGuard VPN**. Ayrı bir Register
sekmesi yoktur. Arayüz eski görünüyorsa tam yenileme yapın. API/web güncellenmeden
yalnızca host scriptlerini kopyalamak yeni düğmeyi göstermez.

## 5. Manuel kayıt — ilk cihazı adım adım ekleyin

### 5.1 Kimliği cihazda oluşturun

GUI'de **Create identity manually** → **Download registration request** kullanın.
CLI karşılığı:

```bash
cd /opt/kronoskvm
sudo python3 scripts/infrabox-wireguard.py identity
sudo python3 scripts/infrabox-wireguard.py request > infrabox-registration.json
```

`identity` tekrar çalışınca mevcut kimliği korur; anahtarı döndürmez. Public JSON;
`device_id`, `hostname`, `public_key`, `request_id` ve `version` içerir. Dosyayı
onaylı yönetim kanalıyla sunucu yöneticisine verin. Private key cihazda kalır.

### 5.2 Sunucuda cihazı onaylayın

JSON'daki seri numarası ve cihaz adını fiziksel envanterle karşılaştırın. Sunucuda:

```bash
sudo /usr/local/sbin/kdx-wg-server.sh add \
  --request /root/infrabox-registration.json \
  --endpoint vpn.example.com:51820 > approved-registration.json
```

Araç ilk boş adresi tahsis eder. Belirli bir adres istiyorsanız **ilk kayıt sırasında**:

```bash
sudo /usr/local/sbin/kdx-wg-server.sh add \
  --request /root/infrabox-registration.json \
  --endpoint vpn.example.com:51820 \
  --ip 10.77.0.42 > approved-registration.json
```

`--ip` değeri CIDR içermez. Yanıtta adres `/32` olarak döner. Adres havuz dışında,
dolu veya mevcut bir peer'ın AllowedIPs aralığında ise işlem reddedilir.
Aynı isteği başarıdan sonra tekrar `add` etmeyin; yanıtı kaybettiyseniz `export`
kullanın. İki komut aynı cihaz için alternatif örneklerdir; art arda çalıştırmayın.

### 5.3 Onaylı yanıtı içe alın

GUI'de **Approved registration response → Import registration** seçin. CLI:

```bash
cd /opt/kronoskvm
sudo python3 scripts/infrabox-wireguard.py import approved-registration.json
```

İçe alma, cihaz kimliği ve request UUID'sini doğrular; başka kutuya ait JSON kabul
edilmez. Açık VPN varken profil değiştirilmez; önce Disconnect yapın. Kayıt işlemi
VPN'i kendi başına açmaz.

### 5.4 Bağlantıyı ve açılış tercihini seçin

```bash
sudo python3 /opt/kronoskvm/scripts/infrabox-wireguard.py connect
sudo python3 /opt/kronoskvm/scripts/infrabox-wireguard.py status
sudo python3 /opt/kronoskvm/scripts/infrabox-wireguard.py disconnect
```

GUI'deki Connect/Disconnect aynı kontrolcüyü kullanır. Açılış tercihi ayrı ayardır:

```bash
sudo python3 /opt/kronoskvm/scripts/infrabox-wireguard.py boot-on
sudo python3 /opt/kronoskvm/scripts/infrabox-wireguard.py boot-off
```

**Disconnect, automatic startup tercihini kapatmaz.** Sonraki açılışta da kapalı
kalmasını istiyorsanız `boot-off` veya GUI'deki ilgili checkbox'ı kullanın.

## 6. Otomatik kayıt — Generate & Register

Bu akış için önce yönetici cihaz başına **süreli, tek kayıtlık yetki** verir.
Sonrasında operatör GUI'de tek düğmeyle kayıt olur. Root parolası GUI'ye veya
Infrabox transport konfigürasyonuna yazılmaz. Varsayılan yetki 15 dakika,
yapılandırılabilir aralık 1–30 dakikadır.

### 6.1 Sunucunun SSH host public key'ini güvenilir kanaldan alın

Sunucuda:

```bash
sudo cat /etc/ssh/ssh_host_ed25519_key.pub
```

Bu **public** dosyayı yönetici kanalıyla Infrabox'a
`/tmp/approved-server-host-key.pub` olarak aktarın. `ssh-keyscan` çıktısını
bağımsız doğrulama olmadan güvenilir kabul etmeyin; SSH host kontrolünü kapatmayın.

### 6.2 Kayıt erişim yolunu hazırlayın

**Doğrudan erişim varsa**, Infrabox'ta:

```bash
cd /opt/kronoskvm
sudo python3 scripts/configure-auto-enrollment.py prepare \
  --host SERVER_SSH_HOST --port 22 \
  --host-key-file /tmp/approved-server-host-key.pub \
  > enrollment-transport.pub
```

`--host` WireGuard dış endpoint'i olmak zorunda değildir. Bu adresin SSH portuna
kutudan erişilebilmelidir. Örneğin ayrı yönetim ağı veya SSH için farklı dış port
varsa `--port 2222` kullanılabilir. WG UDP portunu burada vermeyin.

**Sunucuya yalnızca yönetici bilgisayarının VPN'iyle erişiliyorsa**, yönetici
bilgisayarında şu geçici tüneli açın ve kayıt tamamlanana kadar açık bırakın:

```bash
ssh -N -T -o ExitOnForwardFailure=yes \
  -R 127.0.0.1:45222:SERVER_MGMT_IP:22 kronosdx@INFRABOX_IP
```

Ardından Infrabox'ta `prepare` komutunu şu adresle kullanın:

```bash
cd /opt/kronoskvm
sudo python3 scripts/configure-auto-enrollment.py prepare \
  --host 127.0.0.1 --port 45222 \
  --host-key-file /tmp/approved-server-host-key.pub \
  > enrollment-transport.pub
```

Tünel yalnızca kutunun localhost'unda dinler. İçerideki SSH bağlantısı gerçek
sunucunun public host key'ini doğrulamaya devam eder. Yeni internet SSH kuralı
veya müşteri ağ rotası gerekmez. Tüneldeki `SERVER_MGMT_IP:22` kısmını, yönetici
bilgisayarının eriştiği sunucu/SSH portuyla değiştirin.

### 6.3 Sunucuda süreli yetki verin

`enrollment-transport.pub` dosyasını sunucuya aktarın. Cihazın gerçek seri/adını
kullanarak:

```bash
sudo /usr/local/sbin/kdx-wg-enroll.py authorize \
  --device-id DEVICE_SERIAL --hostname DEVICE_HOSTNAME \
  --ssh-public-key-file /root/enrollment-transport.pub \
  --endpoint vpn.example.com:51820 \
  --ttl 900 > approved-enrollment-grant.json
```

`DEVICE_SERIAL` tam 16 karakterlik küçük harfli hexadecimal kart seri numarasıdır;
örnek `100000001234abcd`. Örnek hostname `infrabox-1234abcd` olabilir. Tahmini değer
kullanmayın; cihazın Dashboard bilgisi veya public kayıt isteğiyle doğrulayın.

Yetki JSON'undaki `lease_id` değerini saklayın. Bu JSON private key içermez;
ancak onaylı yönetim kanalıyla ilgili kutuya ulaştırılmalıdır. Saatlerin doğru
olması gerekir; sunucu ve Infrabox NTP durumunu kontrol edin.

### 6.4 Yetkiyi kutuda etkinleştirin ve düğmeye basın

```bash
cd /opt/kronoskvm
sudo python3 scripts/configure-auto-enrollment.py authorize \
  --grant /tmp/approved-enrollment-grant.json
```

GUI'de **Settings → WireGuard VPN → Generate & Register** seçin. CLI karşılığı:

```bash
sudo python3 /opt/kronoskvm/scripts/infrabox-wireguard.py auto-register
```

Akış: yerel WG anahtarı → public istek → kısıtlı SSH komutu → sunucuda IP tahsisi
→ public yanıt → yerel profil. Anahtar zaten varsa korunur. Kayıttan sonra
Generate & Register pasifleşir; sonraki işlem Connect'tir. Manuel kayıt de kalır.

Yanıt kaybolursa aynı istek tekrar okunur, ikinci peer oluşturulmaz. Başka istek
veya başka cihaz reddedilir. Doğrulanmış yanıt yerelde önbelleğe alındığından yerel
kurulum hatası sonrası yeni peer yaratmadan tekrar denenebilir.

### 6.5 Geçici yetkiyi kapatın

Başarılı kayıttan sonra sunucuda:

```bash
sudo /usr/local/sbin/kdx-wg-enroll.py revoke --lease LEASE_UUID
```

Yönetici bilgisayarındaki geçici tüneli `Ctrl+C` ile kapatın. Bu işlem **VPN peer'ını
silmez**; yalnızca kayıt yetkisini kaldırır. Aynı transport public key için yeniden
yetki verecekseniz önce eski grant'i revoke edin. Anahtarın süresi dolmuş olsa bile
eski authorized-key satırı duruyorsa yeni authorize işlemi bunu reddedebilir.

## 7. Özelleştirme: hangisi nereden değişir?

| İhtiyaç | Destek / işlem |
| --- | --- |
| İlk kayıt sırasında sabit cihaz VPN IP'si | Sunucu `add --ip 10.77.0.42` |
| Farklı dağıtım havuzu | Manuel sunucu komutunda `--pool-start`, `--pool-end` |
| Farklı VPN subnet'i | Manuel komutta `--network`; sunucu arayüzü ve istemciler de uyumlu hazırlanmalı |
| Farklı sunucu WG arayüzü | Manuel komutta `--interface`, `--config`, `--registry` birlikte |
| Sunucu dış IP/DNS/UDP portu | Kayıtta `--endpoint`; mevcut cihaz için aşağıdaki yeniden kayıt akışı |
| Kayıt için farklı SSH adresi/portu | Infrabox `prepare --host ... --port ...` |
| Yetki süresi | Sunucu `authorize --ttl 60..1800` |
| Otomatik açılış | GUI checkbox veya `boot-on` / `boot-off` |
| Infrabox Ethernet IP'si | Settings → Network settings → DHCP / Static IPv4 |
| Müşteri LAN erişimi | Ayrı Customer Access ayarı; VPN kaydı otomatik açmaz |

### Farklı pool / subnet / arayüz örneği

**Manuel sunucu aracı** şu parametreleri destekler:

```bash
sudo /usr/local/sbin/kdx-wg-server.sh add \
  --request /root/infrabox-registration.json \
  --endpoint vpn.example.com:51821 \
  --interface wg1 --config /etc/wireguard/wg1.conf \
  --registry /etc/wireguard/kdx-wg1-peers.json \
  --network 10.88.0.0/24 \
  --pool-start 10.88.0.20 --pool-end 10.88.0.200 \
  --ip 10.88.0.42 > approved-registration.json
```

Bu komut `wg1` oluşturmaz ve sunucu arayüz IP'sini değiştirmez. Önce aynı subnet'te
çalışan `wg1` kurulmuş olmalıdır. İlgili `remove`, `status`, `list`, `export`
komutlarında da aynı `--interface`, `--config`, `--registry` değerlerini kullanın.
Mevcut subnet'i taşımak ayrıca planlanan bir ağ bakım işlemidir.

**Otomatik SSH receiver şu an `wg0`, varsayılan registry ve `10.77.0.11–254`
havuzunu kullanır.** GUI'de otomatik pool/subnet seçicisi yoktur. Özel pool veya
sabit IP gereken kurulumda manuel kayıt yolunu kullanın. CLI'deki seçeneklerin
otomatik receiver'a da uygulandığını varsaymayın.

### Mevcut cihazın VPN IP'sini değiştirme

Araçta `update-ip` komutu yoktur. Güncel script sürümünü iki tarafa da yükledikten
sonra onaylı bakımda şu sırayı izleyin. Bu işlem yalnızca ilgili cihazın VPN'ini
keser; yerel Ethernet/AP erişimi elinizde olsun.

1. Cihazda Disconnect yapın. Gerekiyorsa bakım süresince automatic startup'ı kapatın.
2. Varsa önceki enrollment grant'ini revoke edin; eski grant'in yanıtı tekrar kullanılmasın.
3. Cihazın mevcut public kayıt isteğini yeniden dışarı alın; yeni WG anahtarı üretmeyin.
4. Sunucuda **yalnızca bu yönetilen peer'ı** kaldırıp aynı kimliği yeni IP ile ekleyin:

```bash
sudo /usr/local/sbin/kdx-wg-server.sh remove DEVICE_HOSTNAME
sudo /usr/local/sbin/kdx-wg-server.sh add \
  --request /root/infrabox-registration.json \
  --endpoint vpn.example.com:51820 \
  --ip 10.77.0.42 > approved-registration-new.json
```

5. Yeni JSON'u Infrabox GUI'den veya `infrabox-wireguard.py import` ile içe alın.
6. Connect, gerçek handshake ve `https://10.77.0.42` erişimini doğrulayın.
7. Açılış tercihini istediğiniz son duruma getirin.

Yeni IP doluysa `add` reddedilir. Bu durumda eski IP ile yeniden ekleyip eski
profili kullanabilirsiniz; önce güncel envanteri ve yeni adresin boşluğunu kontrol
edin. Her sunucu değişikliği otomatik root-only yedek oluşturur. Private key
korunur. Güncel istemci kontrolcüsü, önceki otomatik kayıt yanıtının önbelleğini de
yeni manuel kayıtla eşitler; eski IP sonraki otomatik denemede geri gelmez.

### Sunucu endpoint IP/DNS/port değişikliği

En kolay yöntem baştan bir DNS adı kullanmaktır. DNS hedefi değiştikten sonra
Disconnect/Connect ile yeniden çözümlemeyi tetikleyin ve handshake'i kontrol edin.

Endpoint metni veya UDP portu değişecekse aynı yeniden kayıt sırasını izleyin;
`add --endpoint YENI_DNS:YENI_UDP_PORT --ip MEVCUT_VPN_IP` kullanın. Böylece sunucu
registry'si, dışa verilen yanıt ve cihaz ayarı aynı kalır. Yalnızca recovery
`.conf` dosyasını elle değiştirmek kalıcı yöntem değildir; kontrolcü üzerine yazabilir.

### Infrabox Ethernet IP'sini değiştirme

GUI'de **Settings → Network settings** altında Ethernet arayüzünü seçin:

- DHCP: adresi ağın DHCP sunucusu verir; sabit kullanım için DHCP reservation da yapılabilir.
- Static IPv4: IP/prefix, aynı subnet'teki gateway ve DNS değerlerini girip uygulayın.

Ethernet IP'si ile VPN IP'si farklıdır; Ethernet değişikliği sunucudaki peer IP'sini
kendiliğinden değiştirmez. Yeni ağ VPN veya `192.168.34.0/24` ile çakışmamalıdır.
Bağlantınız kesilirse yeni adres, cihazın LCD'si, seri tabanlı `.local` adı veya
mevcut yönetim AP'si `192.168.34.100` üzerinden tekrar erişin. Ağ/topolojiye bağlı
mDNS erişimi garanti değildir. Bu adım için `nmcli` ile gelişigüzel AP profili
silmek veya default-route eklemek gerekmez.

## 8. Günlük yönetim ve teşhis

Sunucuda:

```bash
sudo /usr/local/sbin/kdx-wg-server.sh list
sudo /usr/local/sbin/kdx-wg-server.sh status
sudo /usr/local/sbin/kdx-wg-server.sh export DEVICE_HOSTNAME > approved-registration.json
sudo wg show wg0 latest-handshakes
sudo wg show wg0 transfer
```

`list` ve `export` scriptle kaydedilen cihazlar içindir. `status`, önceden mevcut
unmanaged peer'ları da gösterir. `remove` unmanaged peer silmez.

Infrabox'ta:

```bash
sudo python3 /opt/kronoskvm/scripts/infrabox-wireguard.py status
systemctl status kronoskvm-remote-assist-action.path
systemctl status kronoskvm-remote-assist-status.timer
sudo journalctl -u kronoskvm-remote-assist-action.service -n 30 --no-pager
ip -4 route show default
```

Beklenen: gerçek handshake, yalnızca izinli VPN rotaları ve değişmemiş Ethernet/
USB WAN default route. VPN'e bağlı yetkili yönetici bilgisayarında cihazın VPN
IP'siyle GUI'yi açın. Kutunun kendinden imzalı TLS sertifikası için kurumunuzun
normal doğrulama/güven sürecini kullanın; private key'i bilgisayarlara dağıtmayın.

| Sorun | Kontrol |
| --- | --- |
| Register bölümü yok | Settings → WireGuard VPN; yeni API/web image'ları, sayfa tam yenileme |
| Generate & Register pasif | Kayıt zaten tamamlanmış olabilir; yoksa yetki, süre, saat, host modülü ve aktif VPN durumunu kontrol edin |
| SSH timeout | Kutudan SSH erişimi var mı? Yönetici VPN'i yalnızca bilgisayarda olabilir; geçici relay gerekebilir |
| Host key mismatch | İşlemi durdurun; gerçek sunucu anahtarını güvenilir kanaldan doğrulayın |
| Grant expired / revoked | Yeni yönetici onayı; aynı key için önce eski grant'i revoke edin |
| Duplicate kayıt | Başarılı kayıt yanıtı kaybolduysa `export`; yeni peer eklemeyin |
| Waiting for handshake | Forti VIP/policy, dış endpoint/UDP portu, server key ve uplink |
| Profil başka kutuya ait | Serial/public key/request UUID eşleşmiyor; doğru cihazın yanıtını kullanın |
| SaveConfig=true | Önce onaylı bakımda disk/canlı konfigürasyonu uzlaştırın; araç bunu otomatik kapatmaz |
| IP değişikliği reddediliyor | Havuz sınırı, mevcut peer AllowedIPs, adres doluluğu ve çakışan ağlar |

## 9. İptal, yedek ve geri dönüş

VPN erişimini kaldırmak için önce cihazı Disconnect yapın, sonra sunucuda:

```bash
sudo /usr/local/sbin/kdx-wg-server.sh remove DEVICE_HOSTNAME
```

Bu işlem cihazın private key'ini veya uygulamasını silmez. Enrollment grant'ini
iptal etmek başka bir işlemdir; `kdx-wg-enroll.py revoke` VPN peer'ını kaldırmaz.

- Sunucu işlem yedekleri: `/etc/wireguard/kdx-backups/peer-*`.
- Cihaz profil yedekleri: `/etc/kronoskvm/remote-assist/backups/provision-*`.
- Başarısız peer değişikliğinde script önceki dosya/registry/canlı peer durumunu geri alır.
- Başarısız yerel işlemde kontrolcü önceki profile ve tünel durumuna dönmeye çalışır.
- Otomatik rollback de başarısızsa logdaki root-only yedeği kullanarak **ilgili peer'ı**
  uzlaştırın. Diğer peer'ları topluca silmeyin ve çalışan `wg0`'ı yeniden başlatmayın.

Ayrıntılı mimari, API sınırları ve doğrulama kayıtları:
[WireGuard provisioning teknik dokümanı](wireguard-provisioning.md).

## 10. Resmî referanslar

- [Rocky Linux WireGuard kurulumu](https://docs.rockylinux.org/guides/security/wireguard_vpn/)
- [WireGuard kurulum ve araçlar](https://www.wireguard.com/install/)
- [wg komutları](https://git.zx2c4.com/wireguard-tools/about/src/man/wg.8)
- [wg-quick ve SaveConfig](https://git.zx2c4.com/wireguard-tools/about/src/man/wg-quick.8)
- [OpenSSH restrict, forced command ve expiry-time](https://man.openbsd.org/sshd.8#AUTHORIZED_KEYS_FILE_FORMAT)

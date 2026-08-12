# Repetidor Wi-Fi com piCorePlayer + tela TFT (Raspberry Pi 3)

[![Status](https://img.shields.io/badge/status-ativo-brightgreen)](https://github.com/m33600/picoreplayer-wifi-repeater)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%203-c51a4a)](https://github.com/m33600/picoreplayer-wifi-repeater)

Repositório: [github.com/m33600/picoreplayer-wifi-repeater](https://github.com/m33600/picoreplayer-wifi-repeater)

Receita completa para transformar um Raspberry Pi 3 num repetidor Wi-Fi
rodando [piCorePlayer](https://www.picoreplayer.org/) (Tiny Core Linux),
com uma tela TFT SPI mostrando status ao vivo (uplink, AP, clientes
conectados, sinal, tráfego, uptime).

![Tela de status do repetidor](docs/tela-status.png)

*Captura exata do frame renderizado por `pcp-status-display.py` (gerada
chamando a própria função de desenho do script, não uma foto da tela
física).*

## Validação

Testado em 12/08/2026, depois de todas as mudanças (troca de papéis das
interfaces incluída):

- `hostapd`, `dnsmasq`, `wpa_supplicant` e `pcp-status-display.py` rodando
  havia ~23 minutos sem reiniciar (mesmos PIDs desde o último boot, sem
  crashes)
- Cliente real conectado e estável durante todo o período
- Sem erros nos logs — só eventos normais de conexão/associação
- Teste de ponta a ponta (gateway do AP → internet via NAT): **0% de
  perda de pacote**

## Hardware usado

- Raspberry Pi 3 Model B
- Tela **Waveshare 3.5" RPi LCD (A)** — controlador **ILI9486**, touch **XPT2046**
- Dongle USB Wi-Fi **MediaTek MT7601U** (só 802.11b/g/n em modo cliente,
  **sem suporte a AP** — ver nota abaixo) como uplink
- Wi-Fi interno do Pi 3 (chip Broadcom, driver `brcmfmac`, suporta 802.11n)
  como AP

> Já testamos dois dongles Ralink (`rt2800usb`: RT2870 e RT73) como AP —
> ambos tinham bugs reais em modo AP (travava com certos clientes, ou
> beacon no ar sem passar tráfego). O chip **interno do Pi 3 como AP** foi
> o único candidato 100% estável nos nossos testes — daí a troca.

## Topologia

```
Rede existente (ex: roteador de casa)
        |  (Wi-Fi, modo cliente/STA)
     wlan1 (dongle MT7601U)
        |
   [Raspberry Pi 3 / piCorePlayer]
        |
     wlan0 (chip interno, modo AP via hostapd)
        |  (Wi-Fi, SSID do repetidor)
   Dispositivos clientes
```

Repetidor Wi-Fi "de verdade" (sem cabo) precisa de **dois rádios** — um
cliente (STA) e um AP — porque não dá pra fazer bridge de camada 2 entre
duas interfaces Wi-Fi (limitação do formato de frame 802.11). Por isso o
tráfego passa por **NAT**, não por bridge.

**Antes de decidir qual dongle faz qual papel**, confira o suporte real a
modo AP do driver com `iw phy <phyN> info | grep -A5 "Supported interface
modes"` — muita placa "genérica" USB só lista `managed`/`monitor` (sem
`AP`), então só serve pro papel de uplink/cliente. Foi assim que
descobrimos que o MT7601U não serve como AP (driver mainline `mt7601u`
nunca implementou modo AP), mas serve perfeitamente como uplink.

## Por que não usar o `pcp-apmode` pronto

O piCorePlayer tem uma extensão oficial (`pcp-apmode.tcz`) para modo AP,
mas o script dela (`/usr/local/bin/pcp-apmode`) vem com `wlan0` e `eth0`
**fixos no código** — ela assume que o AP é sempre `wlan0` e o uplink é
sempre `eth0` (cabo). Isso não serve para o cenário de dois rádios Wi-Fi
(uplink sem fio). Solução: usar os mesmos binários que essa extensão traz
como dependência (`hostapd`, `dnsmasq`, `iptables`) mas com um script
próprio (`scripts/pcp-repeater-start.sh`).

## A tela: por que driver em userspace

O overlay de device tree `piscreen` (usado por várias telas TFT SPI,
inclusive clones da Waveshare 3.5" A) carrega normalmente, mas **não
existe o módulo de kernel `fbtft`** em nenhuma versão do piCorePlayer
(32 nem 64 bits) — o kernel Linux vem descontinuando esse framework desde
a 5.4. Sem esse driver, `/dev/fb1` nunca é criado.

Solução: desenhar direto na tela via SPI em **userspace**, com Python +
[`pyili9486`](https://github.com/SirLefti/Python_ILI9486) + `spidev` +
`lgpio`, sem depender de nenhum driver de kernel.

Pinout real (lido diretamente do device tree aplicado, `piscreen@0`):

| Sinal | GPIO |
|---|---|
| DC (data/command) | 24 |
| RESET | 25 |
| Backlight | 22 |
| Touch IRQ (não usado ainda) | 17 |

## Passo a passo

### 1. Gravar a imagem

Baixe o piCorePlayer (64-bit para Pi 3/4) e grave no cartão SD:

```sh
xzcat piCorePlayer-XX.X.X-64Bit.img.xz | sudo dd of=/dev/mmcblkX bs=4M status=progress conv=fsync
```

### 2. Configurar a tela (antes ou depois do primeiro boot)

Editar `config.txt` na partição de boot (FAT32) — ver `config/config.txt`
neste repo para o arquivo completo, o trecho relevante é:

```
dtparam=spi=on
dtoverlay=piscreen,speed=24000000
```

Editar `cmdline.txt` (mesma partição), acrescentando ao final da linha
única existente:

```
fbcon=map:10 fbcon=font:VGA8x8
```

### 3. Configurar o Wi-Fi de uplink

Copiar `config/wpa_supplicant.conf.example` para `wpa_supplicant.conf` na
partição de boot, preenchendo `ssid`/`psk` reais. Esse arquivo é
compartilhado entre interfaces — serve tanto se o uplink for `wlan0`
quanto `wlan1`.

Se o uplink for num dongle USB (`wlan1`, não o chip interno), é preciso
também impedir que o piCorePlayer suba `wpa_supplicant` sozinho no
`wlan0` no boot (ele faz isso incondicionalmente quando `WIFI="on"`).
Editar `/usr/local/etc/pcp/pcp.cfg`:

```
WIFI="off"
```

O uplink em `wlan1` é então iniciado manualmente dentro do
`scripts/pcp-repeater-start.sh`, reaproveitando o mecanismo genérico do
próprio piCorePlayer:

```sh
/usr/local/etc/init.d/wifi wlan1 start
```

(esse script aceita `wlan0` ou `wlan1` como parâmetro e já cuida do
`wpa_supplicant` + DHCP — só o `pcp_startup.sh` que vem com `wlan0`
fixo no código).

### 4. Instalar Python e dependências da tela (via SSH, depois do boot)

```sh
tce-load -wi python3.11.tcz python3.11-pip.tcz python3.11-dev.tcz python3.11-rpi-gpio.tcz compiletc.tcz
python3.11 -m pip install spidev pillow 'pyili9486[lgpio]'
```

### 5. Instalar as dependências do repetidor

```sh
tce-load -wi pcp-apmode.tcz iw.tcz
```
(isso já traz `hostapd`, `dnsmasq`, `iptables`, `bridge-utils` como
dependência — não é necessário usar o `pcp-apmode` em si).

### 6. Configurar hostapd/dnsmasq

Editar `/usr/local/etc/pcp/hostapd.conf` e `/usr/local/etc/pcp/dnsmasq.conf`
conforme `config/hostapd.conf` e `config/dnsmasq.conf` deste repo —
`interface=wlan0` (AP no chip interno), ajustar SSID/senha. Se o AP for
no chip interno do Pi 3 (que suporta 802.11n), vale habilitar:

```
ieee80211n=1
ht_capab=[HT40][SHORT-GI-20][DSSS_CCK-40]
```

Se o AP for num dongle sem suporte a "n" (ex: RT73, só b/g), deixar
`ieee80211n=0` — senão o `hostapd` falha ao subir com
`Could not set channel for kernel driver`.

### 7. Scripts de inicialização

Copiar `scripts/pcp-repeater-start.sh` e `scripts/pcp-status-display.py`
para `/opt/` no Pi (⚠️ **não** usar `/usr/local/bin` — no Tiny Core,
`/usr/local` é reconstruído do zero a cada boot a partir das extensões
`.tcz`; só `/opt`, `/home` e alguns caminhos específicos de
`/usr/local/etc/pcp` sobrevivem via backup).

`pcp-repeater-start.sh` já cuida de subir o uplink (`wlan1`, via
`/usr/local/etc/init.d/wifi wlan1 start`) antes de configurar o AP
(`wlan0`) e o NAT — ajustar as variáveis `UPLINK`/`APIF` no topo do
script conforme qual interface faz qual papel no seu caso.

Chamar os dois scripts a partir do `/opt/bootlocal.sh` (ver
`config/bootlocal.sh` para o trecho completo), com espera pela interface
de uplink existir antes de iniciar o repetidor.

### 8. Persistir

```sh
sudo filetool.sh -b
```

## Pegadinhas que valem a pena saber

- **PATH em sessão SSH não-interativa não inclui `/usr/local/sbin` nem
  `/usr/local/bin`** — `iptables`, `iw`, `iwconfig` etc. dão "not found"
  a menos que se use o caminho completo ou exporte o PATH manualmente.
- **`pkill -f <padrão>` pode se automatar** — se o próprio comando SSH
  contém o texto do padrão como argumento, o `pkill` bate no processo do
  próprio comando e mata a sessão antes de qualquer saída (erro 255 sem
  mensagem nenhuma). Usar `killall <nome-do-processo>` em vez disso.
- **`pip install --user`** (padrão quando não é root) instala em
  `~/.local/...` — se o processo que usa essas libs depois roda como
  root (ex: via `bootlocal.sh`), precisa `HOME=/home/tc` explícito na
  chamada, senão dá `ModuleNotFoundError`.
- **`dnsmasq` precisa de `/var/lib/misc` existir** para o arquivo de
  leases — não é criado automaticamente.
- **Sistema roda em UTC sem tzdata** — mais simples aplicar offset fixo
  no próprio script Python do que instalar timezone database (Brasil não
  tem horário de verão desde 2019, então um offset fixo é seguro).
- **Cuidado ao trocar qual interface é uplink vs AP por SSH**: se você
  estiver conectado via SSH pela própria interface que vai virar AP
  (ex: `wlan0`), matar o `wpa_supplicant`/`dhcpcd` dela **corta sua
  própria sessão** no meio da reconfiguração — e você perde acesso antes
  de terminar. Jeito seguro: preparar **todas** as mudanças de config só
  em arquivos (sem matar nenhum processo ao vivo) e aplicar tudo de uma
  vez com um único reboot controlado no final. Se algo não foi
  persistido ainda (`filetool.sh -b`), um religamento de energia volta
  pro último estado salvo — rede de segurança de graça.

## Créditos

- [piCorePlayer](https://www.picoreplayer.org/) / [Tiny Core Linux](http://tinycorelinux.net/)
- [pyili9486](https://github.com/SirLefti/Python_ILI9486) — driver ILI9486 em userspace

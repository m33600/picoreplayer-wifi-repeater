#!/usr/bin/env python3.11
import re
import subprocess
import time
import lgpio
from spidev import SpiDev
from pyili9486.gpio.lgpio_facade import LGPIOFacade
from pyili9486 import ILI9486
from PIL import Image, ImageDraw, ImageFont

DC_PIN, RS_PIN = 24, 25
BL_PIN = 22
SPI_BUS, SPI_DEVICE = 0, 0

IW = '/usr/local/sbin/iw'
HOSTAPD_CLI = '/usr/local/bin/hostapd_cli'

# Sistema roda em UTC (sem tzdata instalada). Brasil nao tem horario de
# verao desde 2019, entao um offset fixo e seguro.
TZ_OFFSET_HOURS = -3

def sh(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ''

def human_bytes(n):
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.0f}{unit}' if unit == 'B' else f'{n:.1f}{unit}'
        n /= 1024
    return f'{n:.1f}TB'

def fit_text(d, font, text, max_width):
    if d.textlength(text, font=font) <= max_width:
        return text
    while text and d.textlength(text + '…', font=font) > max_width:
        text = text[:-1]
    return text + '…'

def get_ip(iface):
    out = sh(f'ifconfig {iface}')
    m = re.search(r'inet addr:([0-9.]+)', out)
    return m.group(1) if m else '---'

def get_uplink_ssid_signal():
    out = sh(f'{IW} dev wlan1 link')
    ssid_m = re.search(r'SSID:\s*(.+)', out)
    sig_m = re.search(r'signal:\s*(-?\d+)\s*dBm', out)
    ssid = ssid_m.group(1).strip() if ssid_m else '---'
    dbm = int(sig_m.group(1)) if sig_m else None
    return ssid, dbm

def signal_quality_percent(dbm):
    if dbm is None:
        return 0
    pct = 2 * (dbm + 100)
    return max(0, min(100, pct))

def signal_color(pct):
    if pct < 35:
        return (220, 60, 60)
    elif pct < 65:
        return (230, 190, 50)
    else:
        return (70, 200, 90)

def draw_signal_bar(d, x, y, w, h, dbm):
    pct = signal_quality_percent(dbm)
    color = signal_color(pct)
    d.rectangle((x, y, x + w, y + h), outline=(120, 120, 120))
    fill_w = int(w * pct / 100)
    if fill_w > 0:
        d.rectangle((x, y, x + fill_w, y + h), fill=color)

def get_client_stats():
    out = sh(f'{HOSTAPD_CLI} -p /var/run/hostapd all_sta')
    stats = {}
    mac_re = re.compile(r'^([0-9a-f]{2}(:[0-9a-f]{2}){5})$', re.IGNORECASE)
    current_mac = None
    rx = tx = 0
    signal = None
    for line in out.splitlines():
        m = mac_re.match(line.strip())
        if m:
            if current_mac:
                stats[current_mac] = (rx + tx, signal)
            current_mac = line.strip().lower()
            rx = tx = 0
            signal = None
            continue
        if line.startswith('rx_bytes='):
            rx = int(line.split('=', 1)[1])
        elif line.startswith('tx_bytes='):
            tx = int(line.split('=', 1)[1])
        elif line.startswith('signal='):
            try:
                signal = int(line.split('=', 1)[1])
            except ValueError:
                signal = None
    if current_mac:
        stats[current_mac] = (rx + tx, signal)
    return stats

def get_clients():
    clients = []
    try:
        with open('/var/lib/misc/dnsmasq.leases') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 4:
                    mac = parts[1].lower()
                    ip = parts[2]
                    name = parts[3] if parts[3] != '*' else mac
                    clients.append((name, ip, mac))
    except Exception:
        pass
    return clients

def local_time_str():
    t = time.time() + TZ_OFFSET_HOURS * 3600
    return time.strftime('%d/%m/%Y %H:%M:%S', time.gmtime(t))

def uptime_str():
    try:
        with open('/proc/uptime') as f:
            secs = float(f.read().split()[0])
    except Exception:
        return '--'
    secs = int(secs)
    d, secs = divmod(secs, 86400)
    h, secs = divmod(secs, 3600)
    m, _ = divmod(secs, 60)
    if d > 0:
        return f'{d}d{h:02d}h{m:02d}m'
    return f'{h:02d}h{m:02d}m'

def build_frame(width, height, font, font_sm, font_b):
    img = Image.new('RGB', (width, height), (10, 10, 30))
    d = ImageDraw.Draw(img)
    y = 4
    d.text((10, y), 'Repetidor piCorePlayer', font=font_b, fill=(255, 255, 0)); y += 18
    d.line((10, y, width-10, y), fill=(80,80,80)); y += 5

    uplink_ssid, uplink_dbm = get_uplink_ssid_signal()
    BAR_X, BAR_W, BAR_H = 225, 90, 11
    d.text((10, y), 'UP:', font=font_b, fill=(120,200,255))
    ssid_txt = fit_text(d, font, uplink_ssid, BAR_X - 45 - 6)
    d.text((45, y), ssid_txt, font=font, fill=(255,255,255))
    draw_signal_bar(d, BAR_X, y + 2, BAR_W, BAR_H, uplink_dbm)
    dbm_txt = f'{uplink_dbm}dB' if uplink_dbm is not None else '--'
    d.text((BAR_X + BAR_W + 6, y), dbm_txt, font=font_sm, fill=(200,200,200))
    y += 17
    d.text((45, y), get_ip('wlan1'), font=font_sm, fill=(150,150,150)); y += 18

    d.text((10, y), 'AP:', font=font_b, fill=(120,255,150))
    ap_ssid_txt = fit_text(d, font, 'RepetidorPicorePlayer', 190)
    d.text((45, y), ap_ssid_txt, font=font, fill=(255,255,255))
    d.text((250, y), '10.10.10.1', font=font_sm, fill=(150,150,150))
    y += 20

    clients = get_clients()
    client_stats = get_client_stats()
    d.text((10, y), f'Clientes conectados: {len(clients)}', font=font_b, fill=(255,180,120)); y += 17

    row_h = 15
    bottom_reserved = 16
    max_rows = max(0, (height - bottom_reserved - y) // row_h)
    shown = clients[:max_rows]

    CBAR_X, CBAR_W, CBAR_H = 320, 40, 8

    for name, ip, mac in shown:
        total, csignal = client_stats.get(mac, (None, None))
        total_s = human_bytes(total) if total is not None else '---'
        name_txt = fit_text(d, font_sm, name, 100)
        d.text((14, y), name_txt, font=font_sm, fill=(230,230,230))
        d.text((120, y), ip, font=font_sm, fill=(180,200,230))
        d.text((215, y), total_s, font=font_sm, fill=(180,230,180))
        draw_signal_bar(d, CBAR_X, y + 2, CBAR_W, CBAR_H, csignal)
        cdbm_txt = f'{csignal}' if csignal is not None else '--'
        d.text((CBAR_X + CBAR_W + 5, y), cdbm_txt, font=font_sm, fill=(180,180,180))
        y += row_h
    if len(clients) > len(shown):
        d.text((14, y), f'+{len(clients)-len(shown)} mais...', font=font_sm, fill=(150,150,150))

    footer = f'{local_time_str()}   Uptime: {uptime_str()}'
    d.text((10, height-16), footer, font=font_sm, fill=(120,120,120))
    return img

def main():
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, BL_PIN, 1)

    spi = SpiDev()
    spi.open(SPI_BUS, SPI_DEVICE)
    spi.mode = 0b10
    spi.max_speed_hz = 24000000

    gpio_facade = LGPIOFacade(DC_PIN, RS_PIN)
    lcd = ILI9486(spi, gpio_facade)
    lcd.begin()
    width, height = lcd.dimensions

    font = ImageFont.load_default(size=13)
    font_sm = ImageFont.load_default(size=11)
    font_b = ImageFont.load_default(size=14)

    while True:
        frame = build_frame(width, height, font, font_sm, font_b)
        lcd.display(frame, 0, 0)
        time.sleep(5)

if __name__ == '__main__':
    main()

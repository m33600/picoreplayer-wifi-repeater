#!/bin/sh
export PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/bin:$PATH

IW=/usr/local/sbin/iw
HOSTAPD_CLI=/usr/local/bin/hostapd_cli
AP_SSID="RepetidorZeroW"
AP_IP="10.10.10.1"
UPLINK_IF="wlan1"
AP_IF="wlan0"
PING_TARGET="8.8.8.8"

echo "Content-type: text/html; charset=utf-8"
echo ""

# --- coleta de dados ---
LINK_OUT=$($IW dev $UPLINK_IF link 2>/dev/null)
UP_SSID=$(echo "$LINK_OUT" | grep 'SSID:' | sed 's/.*SSID: *//')
UP_SIGNAL=$(echo "$LINK_OUT" | grep 'signal:' | grep -oE -- '-?[0-9]+' | head -1)
UP_RXRATE=$(echo "$LINK_OUT" | grep 'rx bitrate:' | sed 's/.*rx bitrate: *//;s/ *$//')
UP_TXRATE=$(echo "$LINK_OUT" | grep 'tx bitrate:' | sed 's/.*tx bitrate: *//;s/ *$//')
UP_IP=$(ifconfig $UPLINK_IF 2>/dev/null | grep 'inet addr' | sed -n 's/.*inet addr:\([0-9.]*\).*/\1/p')

UPTIME_SECS=$(awk '{print int($1)}' /proc/uptime)
UP_D=$((UPTIME_SECS/86400))
UP_H=$(((UPTIME_SECS%86400)/3600))
UP_M=$(((UPTIME_SECS%3600)/60))
if [ "$UP_D" -gt 0 ]; then
  UPTIME_STR="${UP_D}d ${UP_H}h ${UP_M}m"
else
  UPTIME_STR="${UP_H}h ${UP_M}m"
fi

if ping -c 1 -W 2 $PING_TARGET >/dev/null 2>&1; then
  INTERNET_OK=1
else
  INTERNET_OK=0
fi

# qualidade do sinal (0-100%) a partir do dBm, formula 2*(dbm+100)
signal_pct() {
  dbm="$1"
  [ -z "$dbm" ] && { echo 0; return; }
  pct=$((2 * (dbm + 100)))
  [ "$pct" -lt 0 ] && pct=0
  [ "$pct" -gt 100 ] && pct=100
  echo "$pct"
}
signal_color() {
  pct="$1"
  if [ "$pct" -lt 35 ]; then echo "#dc3c3c"
  elif [ "$pct" -lt 65 ]; then echo "#e6be32"
  else echo "#46c85a"
  fi
}

UP_PCT=$(signal_pct "$UP_SIGNAL")
UP_COLOR=$(signal_color "$UP_PCT")

# --- clientes: junta dnsmasq.leases (mac/ip/hostname) com hostapd_cli (signal/bytes) ---
STA_DATA=$($HOSTAPD_CLI -p /var/run/hostapd all_sta 2>/dev/null)

echo "<!DOCTYPE html>"
echo "<html lang='pt-BR'><head>"
echo "<meta charset='utf-8'>"
echo "<meta http-equiv='refresh' content='10'>"
echo "<meta name='viewport' content='width=device-width, initial-scale=1'>"
echo "<title>Repetidor Zero W - Status</title>"
cat <<'CSS'
<style>
body { background:#0a0a1e; color:#e6e6e6; font-family: -apple-system, Arial, sans-serif; margin:0; padding:16px; }
h1 { color:#ffd633; font-size:1.3em; margin:0 0 4px 0; }
.sub { color:#888; font-size:0.85em; margin-bottom:16px; }
.card { background:#151530; border-radius:8px; padding:14px 16px; margin-bottom:14px; }
.card h2 { margin:0 0 10px 0; font-size:1em; color:#7ac8ff; }
.card h2.ap { color:#78ffa0; }
.row { display:flex; align-items:center; gap:10px; margin:4px 0; flex-wrap:wrap; }
.label { color:#999; min-width:110px; }
.bar-wrap { display:inline-block; width:120px; height:12px; background:#222; border:1px solid #555; border-radius:3px; overflow:hidden; vertical-align:middle; }
.bar-fill { height:100%; }
table { width:100%; border-collapse:collapse; margin-top:6px; }
th, td { text-align:left; padding:6px 8px; font-size:0.9em; border-bottom:1px solid #2a2a4a; }
th { color:#999; font-weight:normal; }
.alert { background:#dc3c3c; color:#fff; padding:12px 16px; border-radius:8px; margin-bottom:14px; font-weight:bold; text-align:center; }
.ok { color:#46c85a; }
.footer { color:#666; font-size:0.8em; margin-top:10px; }
</style>
CSS
echo "</head><body>"
echo "<h1>Repetidor piCorePlayer - Zero W</h1>"
echo "<div class='sub'>Atualiza a cada 10s</div>"

if [ "$INTERNET_OK" -eq 0 ]; then
  echo "<div class='alert'>SEM INTERNET no uplink ($UPLINK_IF) - repetidor sem saida para a web</div>"
fi

echo "<div class='card'>"
echo "<h2>Uplink ($UPLINK_IF)</h2>"
echo "<div class='row'><span class='label'>Rede</span><span>${UP_SSID:-desconectado}</span></div>"
echo "<div class='row'><span class='label'>IP</span><span>${UP_IP:---}</span></div>"
echo "<div class='row'><span class='label'>Sinal</span><span class='bar-wrap'><span class='bar-fill' style='width:${UP_PCT}%;background:${UP_COLOR}'></span></span><span>${UP_SIGNAL:-?} dBm</span></div>"
echo "<div class='row'><span class='label'>Velocidade (link)</span><span>RX ${UP_RXRATE:-?} / TX ${UP_TXRATE:-?}</span></div>"
echo "</div>"

echo "<div class='card'>"
echo "<h2 class='ap'>AP</h2>"
echo "<div class='row'><span class='label'>SSID</span><span>$AP_SSID</span></div>"
echo "<div class='row'><span class='label'>IP</span><span>$AP_IP</span></div>"
echo "</div>"

echo "<div class='card'>"
echo "<h2>Clientes conectados</h2>"
echo "<table><tr><th>Nome</th><th>IP</th><th>Sinal</th><th>Trafego</th></tr>"

# fonte de verdade de quem esta conectado AGORA: hostapd_cli, nao o
# arquivo de leases (que mantem entradas antigas ate expirar, 12h)
STA_LIST=$(echo "$STA_DATA" | awk '
  /^[0-9a-fA-F:]+$/ { if (mac!="") print mac"|"sig"|"rx"|"tx; mac=$0; sig=""; rx=""; tx=""; next }
  /^signal=/ { s=$0; sub("signal=","",s); sig=s }
  /^rx_bytes=/ { s=$0; sub("rx_bytes=","",s); rx=s }
  /^tx_bytes=/ { s=$0; sub("tx_bytes=","",s); tx=s }
  END { if (mac!="") print mac"|"sig"|"rx"|"tx }
')

if [ -n "$STA_LIST" ]; then
  echo "$STA_LIST" | while IFS='|' read -r mac csig crx ctx; do
    [ -z "$mac" ] && continue
    lease=$(grep -i "$mac" /var/lib/misc/dnsmasq.leases 2>/dev/null | head -1)
    ip=$(echo "$lease" | awk '{print $3}')
    hostname=$(echo "$lease" | awk '{print $4}')
    [ -z "$hostname" ] || [ "$hostname" = "*" ] && hostname="$mac"
    [ -z "$ip" ] && ip="--"

    if [ -n "$csig" ] && [ "$csig" != "0" ]; then
      cpct=$(signal_pct "$csig")
      ccolor=$(signal_color "$cpct")
      sigcell="<span class='bar-wrap' style='width:60px'><span class='bar-fill' style='width:${cpct}%;background:${ccolor}'></span></span> ${csig}dBm"
    else
      sigcell="--"
    fi
    if [ -n "$crx" ] && [ -n "$ctx" ]; then
      total=$((crx + ctx))
      total_kb=$((total / 1024))
      trafcell="${total_kb} KB"
    else
      trafcell="--"
    fi
    echo "<tr><td>$hostname</td><td>$ip</td><td>$sigcell</td><td>$trafcell</td></tr>"
  done
else
  echo "<tr><td colspan='4' style='color:#666'>Nenhum cliente conectado agora</td></tr>"
fi
echo "</table>"
echo "</div>"

echo "<div class='footer'>Uptime: $UPTIME_STR | Internet: "
if [ "$INTERNET_OK" -eq 1 ]; then echo "<span class='ok'>OK</span>"; else echo "<span style='color:#dc3c3c'>FALHOU</span>"; fi
echo "</div>"

echo "</body></html>"

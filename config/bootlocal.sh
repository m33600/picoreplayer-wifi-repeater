#!/bin/sh
# put other system startup commands here

GREEN="$(echo -e '\033[1;32m')"

echo
echo "${GREEN}Running bootlocal.sh..."
#pCPstart------
/usr/local/etc/init.d/pcp_startup.sh 2>&1 | tee -a /var/log/pcp_boot.log
#pCPstop------

# Repetidor Wi-Fi (wlan1 uplink -> wlan0 AP via hostapd/dnsmasq/iptables)
(
  CNT=0
  until ifconfig wlan1 2>/dev/null | grep -q 'HWaddr'; do
    CNT=$((CNT+1))
    [ $CNT -gt 40 ] && break
    sleep 1
  done
  sleep 2
  /opt/pcp-repeater-start.sh >> /var/log/pcp_repeater.log 2>&1
) &

# Tela de status do repetidor
(
  sleep 5
  HOME=/home/tc python3.11 /opt/pcp-status-display.py >> /var/log/pcp_status_display.log 2>&1
) &

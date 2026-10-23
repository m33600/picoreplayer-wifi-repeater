#!/bin/sh
export PATH=/usr/local/sbin:/usr/local/bin:$PATH
WIFI_IP=10.10.10.1
HOSTAPDCONF=/usr/local/etc/pcp/hostapd.conf
DNSMASQCONF=/usr/local/etc/pcp/dnsmasq.conf
APIF=wlan0

# Uplink: cabo (eth0) se tiver IP; senao o dongle Wi-Fi (wlan1).
UPLINK=wlan1
for i in 1 2 3 4 5 6 7 8 9 10; do
  if ifconfig eth0 2>/dev/null | grep -q 'inet addr:'; then UPLINK=eth0; break; fi
  sleep 2
done

# Sobe o uplink Wi-Fi (STA) usando o mecanismo nativo do piCorePlayer,
# que ja usa /usr/local/etc/pcp/wpa_supplicant.conf e cuida do DHCP.
[ "$UPLINK" = wlan1 ] && /usr/local/etc/init.d/wifi $UPLINK start

mkdir -p /usr/local/etc/pcp
mkdir -p /var/lib/misc
echo -e "${WIFI_IP}\tpcp" > /usr/local/etc/pcp/pcp_hosts

ifconfig $APIF down
ifconfig $APIF ${WIFI_IP} netmask 255.255.255.0 up

mkdir -p /var/run/hostapd
start-stop-daemon --start --quiet -m -p /var/run/hostapd.pid -b --startas /bin/sh -- -c "exec /usr/local/bin/hostapd ${HOSTAPDCONF} >> /var/log/pcp_hostapd.log"

touch /var/log/pcp_dnsmasq.log
chmod 666 /var/log/pcp_dnsmasq.log
start-stop-daemon --start --quiet -m -p /var/run/dnsmasq.pid -b --exec /usr/local/sbin/dnsmasq -- -C ${DNSMASQCONF}

echo 1 > /proc/sys/net/ipv4/ip_forward
iptables --table nat --flush
iptables -F FORWARD
iptables -t nat -A POSTROUTING -o $UPLINK -j MASQUERADE
iptables -A FORWARD -i $UPLINK -o $APIF -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i $APIF -o $UPLINK -j ACCEPT

#!/bin/bash

set -xeo pipefail

export DEBIAN_FRONTEND=noninteractive
export VENV=/osh-selenium_venv

apt-get update
apt-get -y upgrade
apt-get install --no-install-recommends -y \
  lsb-release \
  gnupg \
  ca-certificates \
  curl \
  unzip \
  wget \
  python3 \
  python3-pip \
  python3-venv \
  jq

install -m 0755 -d /etc/apt/keyrings

curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
  | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg

chmod 0644 /etc/apt/keyrings/google-chrome.gpg

echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
  | tee /etc/apt/sources.list.d/google-chrome.list

cat >/etc/apt/apt.conf.d/99retries-timeouts <<'EOF'
Acquire::Retries "10";
Acquire::https::Timeout "120";
Acquire::http::Timeout "120";
Acquire::ForceIPv4 "true";
EOF

apt-get update
apt-get install --no-install-recommends -y google-chrome-stable

python3 -m venv ${VENV}
source ${VENV}/bin/activate
python -m pip install --upgrade --no-cache-dir pip
python -m pip install --no-cache-dir selenium

CHROME_VERSION=$(dpkg -s google-chrome-stable | grep -Po '(?<=^Version: ).*' | awk -F'.' '{print $1"."$2"."$3}')
echo "Detected Chrome version: ${CHROME_VERSION}"
DRIVER_URL=$(wget -qO- https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json | jq -r --arg chrome_version "$CHROME_VERSION" '.channels | (.Stable, .Beta) | .downloads.chromedriver[] | select(.platform=="linux64" and (.url | test($chrome_version))).url')
echo "Downloading ChromeDriver from: ${DRIVER_URL}"
wget -O /tmp/chromedriver.zip "${DRIVER_URL}"
unzip -j /tmp/chromedriver.zip -d /etc/selenium

apt-get purge --autoremove -y unzip jq
rm -rf /var/lib/apt/lists/* /tmp/*

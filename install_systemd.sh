#! /bin/bash
#first make start sh's 

PYTHON=$(which python3)
echo #PYTHON

#start
echo "#!/bin/bash
$PYTHON not_tunein.py" > nstart.sh


#now making system file

echo "[Unit]
Description=not tunein
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=1
User=$USER
WorkingDirectory=$PWD
ExecStart=/bin/bash $PWD/nstart.sh

[Install]
WantedBy=multi-user.target
" > not_tunein.service

sudo mv not_tunein.service /etc/systemd/system/not_tunein.service

sudo systemctl daemon-reload
sudo systemctl enable not_tunein
sudo systemctl start not_tunein

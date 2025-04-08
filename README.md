Minimum steps after fresh install of bookworm. This works on a Raspberry Pi Zero W 2 with a Pimoroni Pirate Audio DAC (as of 2025.04.07). I could never even get close to getting it to work with the instructions at Pimoroni so github copilot and myself just created something that actually works!

#0 Install all python packages necessary to run the code. You can install these via "apt install python3-xxxx" or pip install. If using pip install, make sure sure you install in a venv. Put all your audio files in a folder named "audio_library" in the same folder as the script.

vlc; Pillow (PIL); RPi.GPIO; st7789; mutagen .....  there will be a few others. make sure to install in the right venv.

===============
#1 - add or change these in /boot/firmware/config.txt
===============
# Disable hdmi audio
dtparam=audio=off
hdmi_ignore_edid_audio=1

# Find this line and add ,noaudio
dtoverlay=vc4-kms-v3d,noaudio

# Enable pirateaudio DAC
dtoverlay=hifiberry-dac
=================
#2 "sudo vim /etc/asound.conf"
===============
pcm.!default {
    type hw
    card sndrpihifiberry
}

ctl.!default {
    type hw
    card sndrpihifiberry
}
===================
#3 - Create a service using systemd to load the app on boot. 
"vim /etc/systemd/system/luffy-player.service"
=============
[Unit]
Description=Luffy Audio Player
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/home/your_username/luffy
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=:0
ExecStart=/bin/bash -c 'source bin/activate && python3 luffy06.py'
Restart=on-failure
RestartSec=5
StandardOutput=append:/home/your_username/luffy/player.log
StandardError=append:/home/your_username/luffy/player.log

[Install]
WantedBy=multi-user.target
======
#4 enable service and test it fires up on boot. check the logs if it does not load.
sudo systemctl enable luffy-player.service
sudo reboot

##Author: Dan Steingart
##Date Started: 2022-08-12
##Notes: Not TuneIn Radio Controller for Sonos,MPD,MQTT version


import paho.mqtt.client as mqtt
import json
import requests
import sys
from subprocess import getoutput as go
from settings import *

if BACKEND == "sonos": from soco import SoCo, discover



if len(sys.argv) > 1:
    try: 
        PORT = int(sys.argv[1])
    except:
        print("port must be an integer, quitting")
        exit()

zs = {}
stations = {}

def zoner():
    if BACKEND == "sonos":
        for zone in discover(allow_network_scan=True):
            print(zone.player_name,zone.ip_address)
            zs[zone.player_name] = zone.ip_address
    if BACKEND == "mpc": zs['mpc'] = 'mpc'

skeys = None    
def stationer():
    global skeys
    surl = STATIONSCSV
    rs = requests.get(surl).text.split("\n")
    rs.pop(0) #assume title, url, notes 
    for r in rs:
        try:
            p = r.split("\t")
            stations[p[0]] = p[1]
        except Exception as E: None
    skeys = list(stations.keys())
    print(skeys)


zoner()

stationer()


def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    client.subscribe(f"{MQTTcmd}/cmd")

def on_message(client, userdata, msg):
    pl = json.loads(msg.payload)
    if "station" in pl: play_station(pl)
    if "cmd" in pl: 
        if pl['cmd'] == "stop":  stop(pl)
        if pl['cmd'] == "vup":   vup(pl)
        if pl['cmd'] == "vdown": vdown(pl)




def play_station(pl):
    try:
        station = skeys[pl['station']]
        if BACKEND == "sonos": 
            zone = pl['room']
            SoCo(zs[zone]).play_uri("x-rincon-mp3radio://"+stations[station],title=station)
            out = {'result':'success','action':f"playing {station} on {zone}"}    
        if BACKEND == "mpc":
            clear_mpc()
            add_mpc(stations[station])
            play_mpc()
            out = {'result':'success','action':f"playing {station}"}    
    except: None


def stop(pl):
    if BACKEND == "sonos": 
        zone = pl['room']
        SoCo(zs[zone]).stop()
        out = {'result':'success','action':f"stopped {zone}"}    
    if BACKEND == "mpc":
        clear_mpc()
        stop_mpc()
        out = {'result':'success','action':f"stopped"}    

def vup(pl):   SoCo(zs[pl['room']]).volume = SoCo(zs[pl['room']]).volume + 5 
def vdown(pl): SoCo(zs[pl['room']]).volume = SoCo(zs[pl['room']]).volume - 5 


def set_volume():
    volume = int(data['volume'])
    if BACKEND == "sonos": 
        zone = data['zone']
        SoCo(zs[zone]).volume = volume
        out = {'result':'success','action':f"{zone} volume set to {volume}"}    
    if BACKEND == "mpc": 
        vol_mpc(volume)
        out = {'result':'success','action':f"volume set to {volume}"}    

    return jsonify(out)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTTaddr, 1883, 60)
client.loop_forever()
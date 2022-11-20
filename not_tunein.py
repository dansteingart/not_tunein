##Author: Dan Steingart
##Date Started: 2022-08-12
##Notes: Not TuneIn Radio Controller for Sonos,MPD

from flask import Flask, jsonify, request
from soco import SoCo, discover
import json
import requests
import sys
from subprocess import getoutput as go
from settings import *

PORT = 9000

if len(sys.argv) > 1:
    try: 
        PORT = int(sys.argv[1])
    except:
        print("port must be an integer, quitting")
        exit()

zs = {}
stations = {}

app = Flask(__name__)

def clear_mpc(): go("mpc clear")

def add_mpc(s): go(f"mpc add {s}")

def play_mpc(): go(f"mpc play")

def stop_mpc(): go(f"mpc stop")

def vol_mpc(i): go(f"mpc volume {i}")

def get_vol_mpc():
    vv = go("mpc volume").split(":")[1].strip().replace("%","")
    return vv

def zoner():
    if BACKEND == "sonos":
        for zone in discover():
            print(zone.player_name,zone.ip_address)
            zs[zone.player_name] = zone.ip_address
    if BACKEND == "mpc": zs['mpc'] = 'mpc'
    
def stationer():
    surl = STATIONSCSV
    rs = requests.get(surl).text.split("\n")
    rs.pop(0) #assume title, url, notes 
    for r in rs:
        try:
            p = r.split("\t")
            stations[p[0]] = p[1]
        except Exception as E: None

zoner()

stationer()

@app.route('/')
def index(): return open("static/index.html").read()

@app.route('/get_zone')
def get_zones(): return jsonify(zs)

@app.route('/get_station')
def get_stations(): return jsonify(stations)

@app.route('/rezone')
def rezone():
    zoner()
    return jsonify(zs)

@app.route('/restation')
def restation():
    stationer()
    return jsonify(stations)


@app.route('/play_station',methods = ['POST'])
def play_station():
    print(request.form)
    data = request.form
    station = data['station']
    if BACKEND == "sonos": 
        zone = data['zone']
        SoCo(zs[zone]).play_uri("x-rincon-mp3radio://"+stations[station],title=station)
        out = {'result':'success','action':f"playing {station} on {zone}"}    
    if BACKEND == "mpc":
        clear_mpc()
        add_mpc(stations[station])
        play_mpc()
        out = {'result':'success','action':f"playing {station}"}    

    return jsonify(out)

@app.route('/stop',methods = ['POST', 'GET'])
def stop():
    print(request.form)
    data = request.form
    if BACKEND == "sonos": 
        zone = data['zone']
        SoCo(zs[zone]).stop()
        out = {'result':'success','action':f"stopped {zone}"}    
    if BACKEND == "mpc":
        clear_mpc()
        stop_mpc()
        out = {'result':'success','action':f"stopped"}    
    return jsonify(out)

@app.route('/sleep',methods = ['POST'])
def sleep():
    data = request.form
    sleep = int(data['sleep'])*60
    if BACKEND == "sonos": 
        zone = data['zone']
        SoCo(zs[zone]).set_sleep_timer(sleep)
        out = {'result':'success','action':f"{zone} sleeping in {data['sleep']} minutes"}    
    return jsonify(out)

@app.route('/set_volume',methods = ['POST'])
def set_volume():
    data = request.form
    volume = int(data['volume'])
    if BACKEND == "sonos": 
        zone = data['zone']
        SoCo(zs[zone]).volume = volume
        out = {'result':'success','action':f"{zone} volume set to {volume}"}    
    if BACKEND == "mpc": 
        vol_mpc(volume)
        out = {'result':'success','action':f"volume set to {volume}"}    

    return jsonify(out)

@app.route('/get_volume',methods = ['POST'])
def get_volume():
    data = request.form
    if BACKEND == "sonos": 
        zone = data['zone']
        out = {'result':'success','action':f"got {zone} volume","volume":SoCo(zs[zone]).volume}    
    if BACKEND == "mpc":
        out = {'result':'success','action':f"got volume","volume":get_vol_mpc()}    

    return jsonify(out)

app.run(port=PORT,host="0.0.0.0")

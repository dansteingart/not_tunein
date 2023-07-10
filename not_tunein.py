##Author: Dan Steingart
##Date Started: 2022-08-12
##Notes: Not TuneIn Radio Controller for Sonos,MPD

from flask import Flask, jsonify, request
import json
import requests
import sys
from subprocess import getoutput as go
from settings import *
from flask_socketio import SocketIO, emit, send
import threading
import time

def setTimeout(delay):
    timer = threading.Timer(delay, stop_mpc)
    timer.start()
    print(f"sleeping in {delay}")
    return timer




if BACKEND == "sonos": from soco import SoCo, discover

KCRW_url = "https://tracklist-api.kcrw.com/Music/"

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
socketio = SocketIO(app)

def clear_mpc(): go("mpc clear")

def add_mpc(s): go(f"mpc add {s}")

def play_mpc(): go(f"mpc play")

def stop_mpc(): go(f"mpc stop")

def vol_mpc(i): go(f"mpc volume {i}")

def get_vol_mpc():
    vv = go("mpc volume").split(":")[1].strip().replace("%","")
    return vv

def get_status_mpc():
    vv = go("mpc current")
    track = {}
    try:
        if vv.find("[SomaFM]") > -1:
            tracks = vv.split("[SomaFM]:")[-1]
            track['artist'] = tracks.split("-")[0].strip() 
            track['title'] = tracks.split("-")[-1].strip()
            track['station'] = vv.split(":")[0]
        elif vv.find("KCRW") > -1:
            track = requests.get(KCRW_url).json()
            track['station'] = "KCRW E24"
        elif vv.find("WNYC") > -1:
            track['station'] = "WNYC"
            track['program'] = vv.split(":")[-1].strip()
        else:
            track['station'] = vv.split(":")[0]
            tracks = vv.split(":")[-1]
            track['artist'] = tracks.split("-")[0].strip() 
            track['title'] = tracks.split("-")[-1].strip()
    except Exception as E: track['artist'] = str(E)
    return track

    

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

@app.route('/mpc_status')
def mpc_status():
    if BACKEND == "mpc": foo = get_status_mpc()
    else: foo = "not mpc"
    return foo



@socketio.on("system_query")
def system_response(data): socketio.emit("system_update",{'system':BACKEND})

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
        try: add_mpc(stations[station])
        except: add_mpc(stations[skeys[int(station)]])
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
        zone = "mpc"
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
    if BACKEND == "mpc": 
        zone = "mpc"
        tt = setTimeout(sleep)
    out = {'result':'success','action':f"{zone} sleeping in {data['sleep']} minutes"}    
    return jsonify(out)

@app.route('/sleepcancel',methods = ['POST'])
def sleepcancel():
    out = {}
    if BACKEND == "mpc": 
        try: 
            tt.cancel()
            sleep_cancel = "worked"
        except: 
            sleep_cancel = "didn't work" 
        out = {'result': sleep_cancel}    
    return jsonify(out)


@app.route('/set_volume',methods = ['POST'])
def set_volume():
    data = request.form
    volume = data['volume']
    if BACKEND == "sonos": 
        volume = int(data['volume'])
        zone = data['zone']
        SoCo(zs[zone]).volume = volume
        socketio.emit("volume",json.dumps({'volume':volume}))
        out = {'result':'success','action':f"{zone} volume set to {volume}"}    
    if BACKEND == "mpc": 
        print(volume)
        vol_mpc(volume)
        vol = get_vol_mpc()
        socketio.emit("volume",{'volume':vol})
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

socketio.run(app,port=PORT,host="0.0.0.0",allow_unsafe_werkzeug=True)

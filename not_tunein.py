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
import sys
from sqlite_utils import Database
from pync import notify

osa = False
pync = False
if "osa" in sys.argv: osa = True
if "pync" in sys.argv: pync = True

def setTimeout(delay):
    timer = threading.Timer(delay, stop_mpc)
    timer.start()
    print(f"sleeping in {delay}")
    return timer


if BACKEND == "sonos": from soco import SoCo, discover

KCRW_url = "https://tracklist-api.kcrw.com/Music/"

PORT = 9000

BURL = "http://localhost:9000"

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

if pync: print("will let you know stuff")

if "mqtt" in sys.argv:
    import paho.mqtt.client as mqtt
    print("doing mqtt stuff!")
    def on_connect(client, userdata, flags, rc):
        print("Connected with result code "+str(rc))

    def on_disconnect(client, userdata, rc):
        print("Disconnected with result code "+str(flags))

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    # client.on_connect = on_connect
    # client.on_disconnect = on_disconnect

def clear_mpc(): 
    go("mpc clear")
    if osa: go("osascript -e 'tell application \"Music\" to stop'")

def add_mpc(s): go(f"mpc add {s}")

def play_mpc(): go(f"mpc play")

def play_osa():
    go("osascript -e 'tell application \"Music\" to play (some track of library playlist 1)'")

def stop_mpc(): go(f"mpc stop")

def vol_mpc(i): 
    go(f"mpc volume {i}")
    if osa: 
        vv = get_vol_mpc()
        go(f"osascript -e 'tell application \"Music\" to set sound volume to {vv}'")

def get_vol_mpc():
    vv = go("mpc volume").split(":")[1].strip().replace("%","")
    return vv

last_track = {}
def get_status_mpc():
    global last_track
    ee = go("mpc")
    if ee.find("CoreAudio") > -1: 
        sv = get_vol_mpc()
        print(go("brew services restart mpd"))
        time.sleep(.3)
        vol_mpc(sv)
    vv = go("mpc current")
    track = {}
    track['station'] = current_station
    try:
        if vv.find("[SomaFM]") > -1:
            tracks = vv.split("[SomaFM]:")[-1]
            track['artist'] = tracks.split("-")[0].strip() 
            track['title'] = tracks.split("-")[-1].strip()
            #track['station'] = vv.split(":")[0]
        elif vv.find("Eclectic") > -1:
            track = requests.get(KCRW_url).json()
            track['station'] = "KCRW E24"
        elif vv.find("WNYC") > -1:
            #track['station'] = "WNYC"
            track['program'] = vv.split(":")[-1].strip()
        else:
            #track['station'] = vv.split(":")[0]
            tracks = vv.split(":")[-1]
            track['artist'] = tracks.split("-")[0].strip() 
            track['title'] = tracks.split("-")[-1].strip()
    except Exception as E: track['artist'] = str(E)
    if osa and current_station == "Apple Music": 
        try:
            vv = go("osascript -e 'tell application \"Music\" to get [artist of current track, name of current track]'")
            parts = vv.split(",")
            track['artist'] = parts[0].strip()
            track['title'] = parts[1].strip()

        except Exception as E: None

    try: 
        if track['title'] != last_track['title'] and track['title']!="" and track['station'].find("http") ==-1:
            print(track)
            track['station'] = current_station
            track['time'] = time.time()
            db  = Database("tracks.db")
            db['tracks'].insert(track,pk='time')
            db.close()
            del(track['time']) #for alert purposes.
            last_track = track

            if "mqtt" in sys.argv:
                client.connect(MQTT_BROKER,MQTT_PORT)
                client.publish(MQTT_TOPIC,json.dumps(track))
                client.disconnect()
    except Exception as E: 
        print(E)
        last_track = track
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
    skeys = None
    surl = STATIONSCSV
    rs = requests.get(surl).text.split("\n")
    rs.pop(0) #assume title, url, notes 
    for r in rs:
        try:
            p = r.split("\t")
            stations[p[0].strip()] = p[1]
        except Exception as E: None
    skeys = list(stations.keys())

zoner()

stationer()

@app.route('/')
def index(): return open("static/index.html").read()

@app.route('/local')
def local(): return open("static/pindex.html").read()


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
    if BACKEND == "mpc": 
        foo = get_status_mpc()
    else: foo = "not mpc"
    return foo



@socketio.on("system_query")
def system_response(data): socketio.emit("system_update",{'system':BACKEND,'station':current_station})

current_station = None

@app.route('/play_station',methods = ['POST'])
def play_station():
    global current_station, state
    state = current_station
    try: data = request.json
    except: data = request.form
    station = data['station']
    current_station = station
    if BACKEND == "sonos": 
        zone = data['zone']
        SoCo(zs[zone]).play_uri("x-rincon-mp3radio://"+stations[station],title=station)
        out = {'result':'success','station':station,'zone':zone}    
    if BACKEND == "mpc":
        clear_mpc()
        try: add_mpc(stations[station])
        except: 
              station = skeys[int(station)]
              #print(station)
              add_mpc(stations[station])
        current_station = station
        if osa and current_station.find("Apple Music") ==0: play_osa()
        else: play_mpc()
        out = {'result':'success','station':station}    
    socketio.emit("play",out)
    if pync: notify(f"Playing {station}",title='NT')
    return jsonify(out)

state = "stopped"

@app.route('/stop',methods = ['POST', 'GET'])
def stop():
    global state
    try: data = request.json
    except: data = request.form
    if BACKEND == "sonos": 
        zone = data['zone']
        SoCo(zs[zone]).stop()
        out = {'result':'success','action':f"stopped {zone}"}    
    if BACKEND == "mpc":
        zone = "mpc"
        state = "stopped"

        clear_mpc()
        stop_mpc()
        out = {'result':'success','action':f"stopped"}  
        if pync: notify("Stopped",title='NT') 
    return jsonify(out)

@app.route('/sleep',methods = ['POST'])
def sleep():
    try: data = request.json
    except: data = request.form
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
    try: data = request.json
    except: data = request.form
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
    try: data = request.json
    except: data = request.form
    if BACKEND == "sonos": 
        zone = data['zone']
        out = {'result':'success','action':f"got {zone} volume","volume":SoCo(zs[zone]).volume}    
    if BACKEND == "mpc":
        out = {'result':'success','action':f"got volume","volume":get_vol_mpc()}    

    return jsonify(out)


status = None

def periodic_task():
    global status
    while True:
        this_status = get_status_mpc()
        if state != "stopped" and this_status != status: 
            try: this_status['time']
            except: None
            status = this_status
            socketio.emit('status', status)
            if pync and (status['title'] is not status['artist']): notify(f"Playing {status['title']} by {status['artist']} on {status['station']}",title='NT',open=BURL)

        time.sleep(2)

# Start the periodic task in a separate thread
threading.Thread(target=periodic_task, daemon=True).start()
if __name__ == '__main__':
    socketio.run(app,port=PORT,host="0.0.0.0",allow_unsafe_werkzeug=True)

##Author: Dan Steingart
##Date Started: 2022-08-12
##Notes: Not TuneIn Radio Controller for Sonos,MPD

import os
import shutil
from flask import Flask, jsonify, request
import json
import requests
import sys
from subprocess import getoutput as go

# Check if settings.py exists, if not copy from example
if not os.path.exists('settings.py'):
    if os.path.exists('settings.py.example'):
        shutil.copy('settings.py.example', 'settings.py')
        print("Created settings.py from settings.py.example")
        print("Please edit settings.py to configure your setup")
    else:
        print("ERROR: settings.py.example not found!")
        sys.exit(1)

from settings import *
from flask_socketio import SocketIO, emit, send
import threading
import time
from sqlite_utils import Database
import yt_dlp

# Set defaults for optional settings if not defined
if 'ENABLE_OSA' not in dir(): ENABLE_OSA = False
if 'ENABLE_PYNC' not in dir(): ENABLE_PYNC = False
if 'ENABLE_MQTT' not in dir(): ENABLE_MQTT = False
if 'PORT' not in dir(): PORT = 9000

# Allow PORT override via command line for backwards compatibility
if len(sys.argv) > 1:
    try:
        PORT = int(sys.argv[1])
    except:
        pass

osa = ENABLE_OSA
pync = ENABLE_PYNC

# Conditionally import pync if enabled
if pync:
    from pync import notify

def setTimeout(delay):
    timer = threading.Timer(delay, stop_mpc)
    timer.start()
    print(f"sleeping in {delay}")
    return timer


if BACKEND == "sonos": from soco import SoCo, discover
if BACKEND == "sonos": from soco import SoCo, discover

KCRW_url = "https://tracklist-api.kcrw.com/Music/"


BURL = f"http://localhost:{PORT}"

zs = {}
stations = {}

app = Flask(__name__)
socketio = SocketIO(app)

if pync: print("will let you know stuff")

if ENABLE_MQTT:
    import paho.mqtt.client as mqtt
    print("doing mqtt stuff!")

    # Set default command topic if not specified
    if 'MQTT_CMD_TOPIC' not in dir():
        MQTT_CMD_TOPIC = MQTT_TOPIC.replace("/record", "/cmd")

    def on_connect(client, userdata, flags, reason_code, properties):
        print("Connected with result code "+str(reason_code))
        client.subscribe(MQTT_CMD_TOPIC)
        print(f"Subscribed to {MQTT_CMD_TOPIC}")

    def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        print("Disconnected with result code "+str(reason_code))

    def on_message(client, userdata, msg):
        """Handle incoming MQTT commands from IR remote"""
        global current_station, state, tt, current_station_idx, current_mqtt_node
        try:
            pl = json.loads(msg.payload)
            print(f"MQTT command received: {pl}")

            # Track the MQTT node for light control
            if "room" in pl:
                current_mqtt_node = pl['room']

            # Handle station selection
            if "station" in pl:
                station_idx = pl['station']
                if station_idx < len(skeys):
                    station = skeys[station_idx]
                    current_station = station
                    current_station_idx = station_idx  # Track for button blinking
                    state = current_station

                    # Get station URL
                    station_url = stations[station]

                    if BACKEND == "sonos":
                        # YouTube URLs not supported on Sonos
                        if is_youtube_url(station_url):
                            print(f"MQTT: YouTube URLs not supported on Sonos")
                            return
                        zone = pl.get('room')
                        if zone and zone in zs:
                            SoCo(zs[zone]).play_uri("x-rincon-mp3radio://"+station_url, title=station)
                            socketio.emit("play", {'result':'success','station':station,'zone':zone})
                    elif BACKEND == "mpc":
                        clear_mpc()
                        # Extract stream URL for YouTube URLs
                        if is_youtube_url(station_url):
                            print(f"MQTT: extracting stream URL for {station}...")
                            stream_url = get_youtube_stream_url(station_url)
                            if stream_url:
                                station_url = stream_url
                            else:
                                print(f"MQTT: Could not extract YouTube stream URL")
                                return
                        add_mpc(station_url)
                        if osa and current_station.find("Apple Music") == 0:
                            play_osa()
                        else:
                            play_mpc()
                        socketio.emit("play", {'result':'success','station':station})
                    print(f"Playing station: {station}")
                    if pync: notify(f"Playing {station}",title='NT')

            # Handle commands
            if "cmd" in pl:
                cmd = pl['cmd']

                if cmd == "stop":
                    state = "stopped"
                    if BACKEND == "sonos":
                        zone = pl.get('room')
                        if zone and zone in zs:
                            SoCo(zs[zone]).stop()
                    elif BACKEND == "mpc":
                        clear_mpc()
                        stop_mpc()
                        # Cancel sleep timer if exists
                        try:
                            if 'tt' in globals():
                                tt.cancel()
                                print("Sleep timer cancelled")
                        except: pass
                    print("Stopped playback")
                    if pync: notify("Stopped",title='NT')

                elif cmd == "vup":
                    if BACKEND == "sonos":
                        zone = pl.get('room')
                        if zone and zone in zs:
                            current_vol = SoCo(zs[zone]).volume
                            new_vol = current_vol + 5
                            SoCo(zs[zone]).volume = new_vol
                            socketio.emit("volume", {'volume': new_vol})
                    elif BACKEND == "mpc":
                        current_vol = int(get_vol_mpc())
                        new_vol = current_vol + 5
                        vol_mpc(new_vol)
                        socketio.emit("volume", {'volume': new_vol})
                    print("Volume up")

                elif cmd == "vdown":
                    if BACKEND == "sonos":
                        zone = pl.get('room')
                        if zone and zone in zs:
                            current_vol = SoCo(zs[zone]).volume
                            new_vol = current_vol - 5
                            SoCo(zs[zone]).volume = new_vol
                            socketio.emit("volume", {'volume': new_vol})
                    elif BACKEND == "mpc":
                        current_vol = int(get_vol_mpc())
                        new_vol = current_vol - 5
                        vol_mpc(new_vol)
                        socketio.emit("volume", {'volume': new_vol})
                    print("Volume down")

                elif cmd == "sleep":
                    sleep_seconds = 60 * 60  # 1 hour
                    if BACKEND == "sonos":
                        zone = pl.get('room')
                        if zone and zone in zs:
                            SoCo(zs[zone]).set_sleep_timer(sleep_seconds)
                            print(f"Sleep timer set for 1 hour on {zone}")
                    elif BACKEND == "mpc":
                        tt = setTimeout(sleep_seconds)
                        print("Sleep timer set for 1 hour")

        except Exception as E:
            print(f"Error processing MQTT message: {E}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    def send_trellis_light(node, button, color, duration_ms):
        """Send a light command to the NeoTrellis via MQTT.

        Args:
            node: The MQTT node name (e.g., "Bedroom")
            button: Button index 0-15
            color: [r, g, b] values 0-255
            duration_ms: milliseconds, -1=indefinite, 0=off
        """
        if not node or button is None:
            return
        topic = f"{node}/lights"
        payload = json.dumps({"button": button, "color": color, "duration_ms": duration_ms})
        try:
            client.publish(topic, payload)
        except Exception as e:
            print(f"Error sending trellis light: {e}")

# YouTube Music support functions
import subprocess

def is_youtube_url(url):
    """Check if URL is a YouTube or YouTube Music URL"""
    youtube_domains = ['youtube.com', 'youtu.be', 'music.youtube.com']
    return any(domain in url for domain in youtube_domains)

def get_youtube_stream_url(url):
    """Get direct stream URL from YouTube using yt-dlp.

    Returns a playable stream URL that MPD/Sonos can use.
    Note: YouTube URLs expire after some time (typically 6 hours).
    """
    try:
        # Use yt-dlp to get the direct stream URL
        # --get-url extracts the actual media URL without downloading
        # --playlist-items 1 gets only the first track from playlists
        cmd = ['yt-dlp', '-f', 'bestaudio', '--get-url', '--playlist-items', '1', url]

        print(f"  Extracting stream URL from YouTube...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if result.returncode == 0:
            # Get the first line that looks like a URL (ignoring warnings)
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('http'):
                    print(f"  ✓ Got stream URL (length: {len(line)} chars)")
                    return line

        print(f"  Error: yt-dlp failed with return code {result.returncode}")
        if result.stderr:
            print(f"  Error output: {result.stderr[:200]}")
        return None

    except subprocess.TimeoutExpired:
        print(f"  Error: yt-dlp timed out after 15 seconds")
        return None
    except Exception as e:
        print(f"  Error extracting YouTube URL: {e}")
        return None

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

            if ENABLE_MQTT:
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

# Track blinking state for alternating colors
_blink_toggle = False

@app.route('/track_status', methods=['POST', 'GET'])
def track_status():
    global _blink_toggle
    track = {}
    if BACKEND == "mpc":
        track = get_status_mpc()
    elif BACKEND == "sonos":
        try:
            data = request.json if request.method == 'POST' else request.args
            zone = data.get('zone')
            if zone and zone in zs:
                track_info = SoCo(zs[zone]).get_current_track_info()
                track['artist'] = track_info.get('artist', '')
                track['title'] = track_info.get('title', '')
                track['album'] = track_info.get('album', '')
                track['station'] = track_info.get('radio_show', current_station or '')
                track['uri'] = track_info.get('uri', '')

                # Blink station button orange/green when buffering/connecting
                # NeoTrellis buttons 0-11 are for stations
                if ENABLE_MQTT and current_station_idx is not None and current_station_idx <= 11:
                    title = track['title']
                    if title.startswith('ZPSTR_BUFFERING') or title.startswith('ZPSTR_CONNECTING'):
                        _blink_toggle = not _blink_toggle
                        if _blink_toggle:
                            send_trellis_light(zone, current_station_idx, [255, 165, 0], 1000)  # orange
                        else:
                            send_trellis_light(zone, current_station_idx, [0, 255, 0], 1000)  # green
            else:
                track['error'] = 'Zone not specified or not found'
        except Exception as E:
            track['error'] = str(E)
    else:
        track['error'] = 'Unknown backend'

    return jsonify(track)



@socketio.on("system_query")
def system_response(data): socketio.emit("system_update",{'system':BACKEND,'station':current_station})

current_station = None
current_station_idx = None  # Track station index for NeoTrellis button
current_mqtt_node = None    # Track the MQTT node for light control

@app.route('/play_station',methods = ['POST'])
def play_station():
    global current_station, state, current_station_idx
    state = current_station
    try: data = request.json
    except: data = request.form
    station = data['station']

    # Convert station index to station name if needed
    if isinstance(station, int) or (isinstance(station, str) and station.isdigit()):
        current_station_idx = int(station)
        station = skeys[current_station_idx]
    else:
        # Look up index by name
        try:
            current_station_idx = skeys.index(station)
        except (ValueError, AttributeError):
            current_station_idx = None

    current_station = station

    # Get the station URL
    station_url = stations[station]

    if BACKEND == "sonos":
        # Check if it's a YouTube URL - not supported on Sonos (URLs expire too quickly)
        if is_youtube_url(station_url):
            out = {'result':'error','message':'YouTube Music is not supported on Sonos (stream URLs expire too quickly for reliable playback)'}
            return jsonify(out)
        zone = data['zone']
        SoCo(zs[zone]).play_uri("x-rincon-mp3radio://"+station_url,title=station)
        out = {'result':'success','station':station,'zone':zone}

    if BACKEND == "mpc":
        clear_mpc()

        # Check if it's a YouTube URL and set up FIFO streaming
        if is_youtube_url(station_url):
            print(f"Detected YouTube URL for {station}, extracting stream URL...")
            stream_url = get_youtube_stream_url(station_url)
            if stream_url:
                station_url = stream_url
            else:
                out = {'result':'error','message':'Could not extract YouTube stream URL'}
                return jsonify(out)

        # Add to MPD and play
        add_mpc(station_url)

        current_station = station
        if osa and current_station.find("Apple Music") ==0:
            play_osa()
        else:
            play_mpc()
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

@app.route('/volume_up',methods = ['GET'])
def volume_up():
    data = request.args
    if BACKEND == "sonos":
        zone = data['zone']
        current_vol = SoCo(zs[zone]).volume
        new_vol = current_vol + 5
        SoCo(zs[zone]).volume = new_vol
        socketio.emit("volume",json.dumps({'volume':new_vol}))
        out = {'result':'success','action':f"{zone} volume up to {new_vol}","volume":new_vol}
    if BACKEND == "mpc":
        current_vol = int(get_vol_mpc())
        new_vol = current_vol + 5
        vol_mpc(new_vol)
        socketio.emit("volume",{'volume':new_vol})
        out = {'result':'success','action':f"volume up to {new_vol}","volume":new_vol}
    return jsonify(out)

@app.route('/volume_down',methods = ['GET'])
def volume_down():
    data = request.args
    if BACKEND == "sonos":
        zone = data['zone']
        current_vol = SoCo(zs[zone]).volume
        new_vol = current_vol - 5
        SoCo(zs[zone]).volume = new_vol
        socketio.emit("volume",json.dumps({'volume':new_vol}))
        out = {'result':'success','action':f"{zone} volume down to {new_vol}","volume":new_vol}
    if BACKEND == "mpc":
        current_vol = int(get_vol_mpc())
        new_vol = current_vol - 5
        vol_mpc(new_vol)
        socketio.emit("volume",{'volume':new_vol})
        out = {'result':'success','action':f"volume down to {new_vol}","volume":new_vol}
    return jsonify(out)

@app.route('/station_up',methods = ['GET'])
def station_up():
    global current_station, state, current_station_idx
    data = request.args

    # Find current station index
    try:
        current_idx = skeys.index(current_station)
    except:
        current_idx = -1

    # Move to next station (wrap around)
    next_idx = (current_idx + 1) % len(skeys)
    station = skeys[next_idx]
    current_station = station
    current_station_idx = next_idx
    state = current_station

    # Get station URL
    station_url = stations[station]

    if BACKEND == "sonos":
        # YouTube URLs not supported on Sonos
        if is_youtube_url(station_url):
            out = {'result':'error','message':'YouTube Music is not supported on Sonos'}
            return jsonify(out)
        zone = data['zone']
        SoCo(zs[zone]).play_uri("x-rincon-mp3radio://"+station_url,title=station)
        out = {'result':'success','station':station,'zone':zone}

    if BACKEND == "mpc":
        clear_mpc()
        # Extract stream URL for YouTube URLs
        if is_youtube_url(station_url):
            print(f"Station Up: extracting stream URL for {station}...")
            stream_url = get_youtube_stream_url(station_url)
            if stream_url:
                station_url = stream_url
            else:
                out = {'result':'error','message':'Could not extract YouTube stream URL'}
                return jsonify(out)
        add_mpc(station_url)
        if osa and current_station.find("Apple Music") == 0:
            play_osa()
        else:
            play_mpc()
        out = {'result':'success','station':station}

    socketio.emit("play",out)
    if pync: notify(f"Playing {station}",title='NT')
    return jsonify(out)

@app.route('/station_down',methods = ['GET'])
def station_down():
    global current_station, state, current_station_idx
    data = request.args

    # Find current station index
    try:
        current_idx = skeys.index(current_station)
    except:
        current_idx = 0

    # Move to previous station (wrap around)
    prev_idx = (current_idx - 1) % len(skeys)
    station = skeys[prev_idx]
    current_station = station
    current_station_idx = prev_idx
    state = current_station

    # Get station URL
    station_url = stations[station]

    if BACKEND == "sonos":
        # YouTube URLs not supported on Sonos
        if is_youtube_url(station_url):
            out = {'result':'error','message':'YouTube Music is not supported on Sonos'}
            return jsonify(out)
        zone = data['zone']
        SoCo(zs[zone]).play_uri("x-rincon-mp3radio://"+station_url,title=station)
        out = {'result':'success','station':station,'zone':zone}

    if BACKEND == "mpc":
        clear_mpc()
        # Extract stream URL for YouTube URLs
        if is_youtube_url(station_url):
            print(f"Station Down: extracting stream URL for {station}...")
            stream_url = get_youtube_stream_url(station_url)
            if stream_url:
                station_url = stream_url
            else:
                out = {'result':'error','message':'Could not extract YouTube stream URL'}
                return jsonify(out)
        add_mpc(station_url)
        if osa and current_station.find("Apple Music") == 0:
            play_osa()
        else:
            play_mpc()
        out = {'result':'success','station':station}

    socketio.emit("play",out)
    if pync: notify(f"Playing {station}",title='NT')
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

# Start MQTT client in background thread if mqtt mode enabled
if ENABLE_MQTT:
    def mqtt_loop():
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            print(f"MQTT connected to {MQTT_BROKER}:{MQTT_PORT}")
            client.loop_forever()
        except Exception as e:
            print(f"MQTT connection error: {e}")

    threading.Thread(target=mqtt_loop, daemon=True).start()
    print("MQTT client started in background")

if __name__ == '__main__':
    socketio.run(app,port=PORT,host="0.0.0.0",allow_unsafe_werkzeug=True)

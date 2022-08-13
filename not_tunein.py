##Author: 
##Date Started:
##Notes:

from flask import Flask, make_response, request, redirect, url_for, abort, session, jsonify, send_file
from soco import SoCo, discover
import json
import requests
import sys

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

def zoner():
    for zone in discover():
        print(zone.player_name,zone.ip_address)
        zs[zone.player_name] = zone.ip_address
    
def stationer():
    surl = "https://docs.google.com/spreadsheets/d/1eCQ94Ur71X0C5-EoPVfuTXJH6f3zYkt1pFmO2872eVs/export?format=tsv"
    rs = requests.get(surl).text.split("\n")
    rs.pop(0) #assume title, url, notes 
    for r in rs:
        try:
            p = r.split("\t")
            stations[p[0]] = p[1]
        except Exception as E: None

zoner()

# the new way
stationer()

# the old way
# stations['Fluid']="https://ice6.somafm.com/fluid-128-mp3"
# stations['Groove Salad Classic']="https://ice6.somafm.com/gsclassic-128-mp3"
# stations['Drone Zone']="https://ice6.somafm.com/dronezone-128-mp3"
# stations["Digitalis"]="https://ice6.somafm.com/digitalis-128-mp3"
# stations['Space Station Soma']="https://ice6.somafm.com/spacestation-128-mp3"

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
    zone = data['zone']
    SoCo(zs[zone]).play_uri("x-rincon-mp3radio://"+stations[station],title=station)
    out = {'result':'success','action':f"playing {station} on {zone}"}    
    return jsonify(out)

@app.route('/stop',methods = ['POST', 'GET'])
def stop():
    print(request.form)
    data = request.form
    zone = data['zone']
    SoCo(zs[zone]).stop()
    out = {'result':'success','action':f"stopped {zone}"}    
    return jsonify(out)

@app.route('/sleep',methods = ['POST'])
def sleep():
    data = request.form
    zone = data['zone']
    sleep = int(data['sleep'])*60
    SoCo(zs[zone]).set_sleep_timer(sleep)
    out = {'result':'success','action':f"{zone} sleeping in {data['sleep']} minutes"}    
    return jsonify(out)

@app.route('/set_volume',methods = ['POST'])
def set_volume():
    data = request.form
    zone = data['zone']
    volume = int(data['volume'])
    SoCo(zs[zone]).volume = volume
    out = {'result':'success','action':f"{zone} volume set to {volume}"}    
    return jsonify(out)

@app.route('/get_volume',methods = ['POST'])
def get_volume():
    data = request.form
    zone = data['zone']
    out = {'result':'success','action':f"got {zone} volume","volume":SoCo(zs[zone]).volume}    
    return jsonify(out)

app.run(port=PORT,host="0.0.0.0")
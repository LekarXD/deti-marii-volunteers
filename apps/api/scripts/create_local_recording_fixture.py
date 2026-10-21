"""Create private loopback-only config files; starts no process and grants no device access."""
import argparse
import json
import os
import secrets
import socket
from pathlib import Path
from urllib.parse import urlsplit

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--database-url',required=True)
    parser.add_argument('--asset-root',required=True)
    parser.add_argument('--renderer-url',default='http://127.0.0.1:5174/recorder.html')
    parser.add_argument('--chrome',required=True)
    args=parser.parse_args()
    database=urlsplit(args.database_url);renderer=urlsplit(args.renderer_url)
    if database.scheme!='postgresql+psycopg' or database.hostname!='127.0.0.1' or database.port!=56147 or database.path not in ('/opora','/opora_recording_proof') or database.password:raise ValueError('Only the explicitly owned local test PostgreSQL cluster is allowed')
    if renderer.scheme!='http' or renderer.hostname!='127.0.0.1' or renderer.path!='/recorder.html' or renderer.username or renderer.password or renderer.query or renderer.fragment:raise ValueError('Only the loopback private renderer is allowed')
    chrome=Path(args.chrome).resolve();asset_root=Path(args.asset_root)
    if not chrome.is_file() or not os.access(chrome,os.X_OK) or not asset_root.is_absolute():raise ValueError('An installed official Chrome and absolute private asset root are required')
    root=Path(args.output).resolve();root.mkdir(mode=0o700,parents=False,exist_ok=False)
    reservations=[]
    try:
        ports=[]
        for kind in (socket.SOCK_STREAM,socket.SOCK_STREAM,socket.SOCK_DGRAM):
            reservation=socket.socket(socket.AF_INET,kind);reservation.bind(('127.0.0.1',0));reservations.append(reservation);ports.append(reservation.getsockname()[1])
        http_port,tcp_port,udp_port=ports
        key='opora-local-'+secrets.token_hex(8);secret=secrets.token_urlsafe(48)
        config={'port':http_port,'bind_addresses':['127.0.0.1'],'rtc':{'tcp_port':tcp_port,'udp_port':udp_port,'use_external_ip':False,'node_ip':'127.0.0.1','enable_loopback_candidate':True},'keys':{key:secret},'logging':{'level':'warn'}}
        env={'OPORA_ENVIRONMENT':'development','OPORA_DATABASE_URL':args.database_url,'OPORA_ASSET_ROOT':str(asset_root),'OPORA_CAPTURE_ENABLED':'true','OPORA_CAPTURE_RENDERER_URL':args.renderer_url,'OPORA_CAPTURE_CHROME_PATH':str(chrome),'OPORA_RTC_URL':f'http://127.0.0.1:{http_port}','OPORA_RTC_PUBLIC_URL':f'ws://127.0.0.1:{http_port}','OPORA_RTC_API_KEY':key,'OPORA_RTC_API_SECRET':secret,'OPORA_RTC_DEPLOYMENT':'self_hosted'}
        for name,value in (('livekit.json',config),('env.json',env)):
            target=root/name
            with target.open('x') as handle:
                os.chmod(target,0o600);json.dump(value,handle);handle.flush();os.fsync(handle.fileno())
        print(json.dumps({'directory':str(root),'rtc_config':str(root/'livekit.json'),'private_env':str(root/'env.json'),'rtc_http_port':http_port,'rtc_tcp_port':tcp_port,'rtc_udp_port':udp_port,'starts_processes':False,'grants_device_access':False}))
    finally:
        for reservation in reservations:reservation.close()

if __name__=='__main__':main()

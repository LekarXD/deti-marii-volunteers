import argparse
import uvicorn

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=7881);args=parser.parse_args()
    uvicorn.run('app.integrations.rtc.sidecar.app:create_app',factory=True,host=args.host,port=args.port,access_log=False,ws='websockets-sansio',ws_max_size=4*1024*1024+1024)
if __name__=='__main__':main()

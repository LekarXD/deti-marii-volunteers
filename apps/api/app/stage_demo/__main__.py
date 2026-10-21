"""Run only inside the designated staging API container as a trusted operator."""
import argparse
import asyncio
import json
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import get_settings
from app.core.model_loader import load_models
from .operator import seed, login_token

async def run(args):
    load_models()
    engine = create_async_engine(get_settings().database_url, hide_parameters=True)
    factory = async_sessionmaker(engine,expire_on_commit=False)
    try:
        async with factory() as db:
            if args.command == 'seed': return await seed(db,args.credentials_path,args.confirm)
            return await login_token(db,args.credentials_path,args.email,UUID(args.challenge_id),args.output_path,args.confirm)
    finally: await engine.dispose()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm',required=True)
    parser.add_argument('--credentials-path',default='/run/opora-private/demo-credentials.json')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('seed')
    token=commands.add_parser('login-token')
    token.add_argument('--email',required=True)
    token.add_argument('--challenge-id',required=True)
    token.add_argument('--output-path',required=True)
    print(json.dumps(asyncio.run(run(parser.parse_args())),ensure_ascii=False))

if __name__=='__main__': main()

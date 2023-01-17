#!/home/brugger/projects/fast/venv/bin/python3
#!/usr/bin/env python3

import re
import argparse
import datetime
from asyncio import ensure_future, gather, get_event_loop, sleep, new_event_loop
from collections import deque
from statistics import mean
from time import time

from aiohttp import ClientSession

MIN_DURATION = 7
MAX_DURATION = 30
STABILITY_DELTA = 2
MIN_STABLE_MEASUREMENTS = 6

total = 0
done = 0
sessions = []

output = None



def timestamp() -> int:
    dt = datetime.datetime.now()
    ts = float(dt.timestamp())
    ts *= 1000000000

    return int(ts)


async def run():
    if output == 'verbose':
        print('fast.com cli')
    token = await get_token()
    urls = await get_urls(token)
    conns = await warmup(urls)
    future = ensure_future(measure(conns))
    result = await progress(future)
    await cleanup()
    if output == 'cli':
        print(f'speed={result:.1f} mbps')

    elif output == 'brief':
        print(f'{result:.2f} mbps')

    elif output == 'mon':
        col = 'red'
        if result > 800:
            col = 'green'
        elif result > 400:
            col = 'orange'
        elif result > 200:
            col = 'coral'            


        print(f"<txt> <span foreground='white' background='{col}'> {result:.2f} mbps </span> </txt>")

        speeds = []
        fh = open('/tmp/fast.log', 'r')
        speeds = [x.rstrip() for x in fh.readlines()]
        speeds.insert(0,f"{result:.2f}")

        fh = open('/tmp/fast.log', 'w')
        fh.write('\n'.join(speeds[:12]))
        fh.close()


        new_line = "\n"

        print(f'<tool>Speeds last 10 min.\n=-=-=-=-=-=-=-=-=-=-=-=-=\n{new_line.join(map(str, speeds[:10]))}</tool>')


    elif output == 'telegraf':
        print(f'net,type=wifi speed={result:.3f} {timestamp()}')

    return


async def get_token():
    async with ClientSession() as s:
        resp = await s.get('https://fast.com/')
        text = await resp.text()
        script = re.search(r'<script src="(.*?)">', text).group(1)

        resp = await s.get(f'https://fast.com{script}')
        text = await resp.text()
        token = re.search(r'token:"(.*?)"', text).group(1)
    dot()
    return token


async def get_urls(token):
    async with ClientSession() as s:
        params = {'https': 'true', 'token': token, 'urlCount': 5}
        resp = await s.get('https://api.fast.com/netflix/speedtest', params=params)
        data = await resp.json()
    dot()
    return [x['url'] for x in data]


async def warmup(urls):
    conns = [get_connection(url) for url in urls]
    return await gather(*conns)


async def get_connection(url):
    s = ClientSession()
    sessions.append(s)
    conn = await s.get(url)
    dot()
    return conn


async def measure(conns):
    workers = [measure_speed(conn) for conn in conns]
    await gather(*workers)


async def measure_speed(conn):
    global total, done
    chunk_size = 64 * 2**10
    async for chunk in conn.content.iter_chunked(chunk_size):
        total += len(chunk)
    done += 1


def stabilized(deltas, elapsed):
    return (
        elapsed > MIN_DURATION and
        len(deltas) > MIN_STABLE_MEASUREMENTS and
        max(deltas) < STABILITY_DELTA
    )


async def progress(future):
    start = time()
    measurements = deque(maxlen=10)
    deltas = deque(maxlen=10)

    while True:
        await sleep(0.2)
        elapsed = time() - start
        speed = total / elapsed / 2**17
        measurements.append(speed)

        if output == "verbose":
            print(f'\033[2K\r{speed:.3f} mbps', end='', flush=True)

        if len(measurements) == 10:
            delta = abs(speed - mean(measurements)) / speed * 100
            deltas.append(delta)

        if done or elapsed > MAX_DURATION or stabilized(deltas, elapsed):
            future.cancel()
            return speed


async def cleanup():
#    print( "closing hanging connections")
    for s in sessions:
        await s.close()
#    await gather(*[s.close() for s in sessions])
    if output == 'verbose':
        print()


def dot():
    if output == 'verbose':
        print('.', end='', flush=True)


def main():
    parser = argparse.ArgumentParser(description="get internet speed from fast.com")
    commands = ["verbose", "telegraf"]  # "release",
    parser.add_argument('command', nargs='*', help="{}".format(",".join(commands)), default=['cli'])
    args = parser.parse_args()

    command = args.command[0]

    global output

    if command == "verbose":
        output = 'verbose'
    elif command == "telegraf":
        output = 'telegraf'
    elif command == "brief":
        output = 'brief'
    elif command == "mon":
        output = 'mon'
    else:
        output = 'cli'

    loop = new_event_loop()
    return loop.run_until_complete(run())


if __name__ == '__main__':
    main()

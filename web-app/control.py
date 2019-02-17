# this is an absolutely terrible way to implement something like this.
# it's only a temporary solution, as it is easier than a re-write of the entire project
# that supports multiple accounts at the same time


from hashlib import sha1
import os
import shutil
import sqlite3
import subprocess
from time import sleep


conn = sqlite3.connect('fundonebot.db')

c = conn.cursor()

keys = ('id', 'api_key', 'api_secret', 'symbol', 'position_size_buy', 'position_size_sell',
        'hedge', 'hedge_side', 'hedge_multiplier', 'stop_limit_multiplier',
        'stop_market_multiplier')

bots_location = os.path.expanduser('/home/ubuntu/')


def create_settings_str(setting) -> str:
    new_settings = ('import logging\n'
            + "BASE_URL = 'https://www.bitmex.com/api/v1/'\n")

    for key in keys:
        new_settings += key.upper() + ' = ' + setting[key] + '\n'

    new_settings += ('LOOP_INTERVAL = .5\n'
            + 'API_REST_INTERVAL = 3\n'
            + 'TIMEOUT = 10\n'
            + 'LOG_LEVEL = logging.INFO\n'
            + "ORDERID_PREFIX = 'mm_'\n")

    return new_settings


def run_loop() -> None:
    while True:
        c.execute('SELECT * FROM settings')

        values = c.fetchall()

        settings = [dict(zip(keys, value)) for value in values]

        print('got settings from db: %s' % settings)

        for setting in settings:
            print('working on setting id: %i' % setting['id'])

            # use id as directory postfix (i.e. fundonebot1, fundonebot4)
            directory = os.path.join(bots_location, 'fundonebot%i/' % setting['id'])

            print(' ~ directory: %s' % directory)

            service_name = 'bitmex-funding%i' % setting['id']
            service_path = '/etc/systemd/system/%s.service' % service_name

            if os.path.exists(directory):
                print(' ~ directory exists, checking if settings have changed')

                # hash current settings file
                settings_path = os.path.join(directory, 'settings.py')

                with open(settings_path, 'r') as f:
                    content = f.read()

                old_hash = sha1(content.encode('utf-8'))

                print(' ~ old hash: %s' % old_hash.hexdigest())

                # create and hash new settings string
                create_settings_str(setting)

                new_hash = sha1(new_settings.encode('utf-8'))

                print(' ~ new hash: %s' % new_hash.hexdigest())

                # if hashes have changed, change settings & restart the bot
                if new_hash != old_hash:
                    print(' ~ hashes have changed, changing settings and restarting')

                    os.remove(settings_path)

                    with open(settings_path, 'w') as f:
                        f.write(new_settings)

                    print(' ~ wrote new settings, restarting')

                    subprocess.run(('sudo systemctl restart %s' % service_name).split())
                    subprocess.run(('sudo systemctl enable %s' % service_name).split())
            else:
                print(' ~ directory doesn\'t exist, creating')

                # create directory
                base_dir = os.path.join(bots_location, 'fundonebot/')
        
                def skip_env(*args):
                    return 'env', '__pycache__'

                shutil.copytree(base_dir, directory, ignore=skip_env)

                print(' ~ initializing virtualenv')

                subprocess.run('virtualenv env'.split(), cwd=directory)

                # create settings file
                settings_str = create_settings_str(setting)

                with open(os.path.join(directory, 'settings.py'), 'w') as f:
                    f.write(settings_str)

                print(' ~ wrote settings.py')

                # create systemd service file
                service_str = ('[Unit]\n'
                        + 'Description=bitmex market bot\n'
                        + 'After=network.target\n\n'
                        + '[Service]\n'
                        + 'User=ubuntu\n'
                        + 'WorkingDirectory=%s\n' % directory
                        + 'ExecStart=%senv/bin/python3 %sstrat.py\n' % (directory, directory)
                        + 'Restart=no\n\n'
                        + '[Install]\n'
                        + 'WantedBy=multi-user.target')

                with open(service_path, 'w') as f:
                    f.write(service_str)

                print(' ~ wrote systemd service file, starting')

                # enable and start systemd service 
                subprocess.run('sudo systemctl daemon-reload'.split())
                subprocess.run(('sudo systemctl start %s' % service_name).split())
                subprocess.run(('sudo systemctl enable %s' % service_name).split())

                print(' ~ started systemd service')

                with open('/home/ubuntu/.bash_aliases', 'r+') as f:
                    if 'monitor%i' % setting['id'] not in f.read():
                        f.write("alias monitor%i='journalctl -fu bitmex-funding%i" %
                                (setting['id'], setting['id']))

                        print(' ~ bash alias "monitor%i" created' % setting['id'])
            
            last_id = setting['id']

        print('last id: %i' % last_id)

        last_id += 1

        while os.path.exists('/etc/systemd/system/bitmex-funding%i.service' % last_id):
            print(' ~ stopping bitmex-funding%i' % last_id)

            subprocess.run(('sudo systemctl stop bitmex-funding%i' % last_id).split())

            subprocess.run(('sudo systemctl disable bitmex-funding%i' % last_id).split())

            last_id += 1

        sleep(5)


if __name__ == '__main__':
    run_loop()

    conn.close()
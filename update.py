import gspread
import youtube_dl
from pathlib import Path
import sys
import datetime
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

gc = gspread.service_account()
sh = gc.open("Bellingcat media archiver")
wks = sh.sheet1
values = wks.get_all_values()

ydl_opts = {'outtmpl': 'tmp/%(id)s.%(ext)s', 'quiet': True}
ydl = youtube_dl.YoutubeDL(ydl_opts)

s3_client = boto3.client('s3',
        region_name=os.getenv('DO_SPACES_REGION'),
        endpoint_url='https://{}.digitaloceanspaces.com'.format(os.getenv('DO_SPACES_REGION')),
        aws_access_key_id=os.getenv('DO_SPACES_KEY'),
        aws_secret_access_key=os.getenv('DO_SPACES_SECRET'))

for i in range(2, len(values)+1):
    v = values[i-1]

    if v[2] == "":
        try:
            info = ydl.extract_info(v[0], download=True)
            filename = ydl.prepare_filename(info)
            key = filename.split('/')[1]

            with open(filename, 'rb') as f:
                s3_client.upload_fileobj(f, Bucket=os.getenv('DO_BUCKET'), Key=key, ExtraArgs={'ACL': 'public-read'})

            os.remove(filename)
            cdn_url = 'https://{}.{}.cdn.digitaloceanspaces.com/{}'.format(os.getenv('DO_BUCKET'), os.getenv('DO_SPACES_REGION'), key)

            update = [{
                'range': 'C' + str(i),
                'values': [['successful']]
            }, {
                'range': 'B' + str(i),
                'values': [[datetime.datetime.now().isoformat()]]
            }, {
                'range': 'D' + str(i),
                'values': [[cdn_url]]
            }]

            wks.batch_update(update)
        except youtube_dl.utils.DownloadError:
            t, value, traceback = sys.exc_info()

            # value is the error that we can update in the sheet
            wks.update('C' + str(i), str(value))
            wks.update('B' + str(i), datetime.datetime.now().isoformat())

            update = [{
                'range': 'C' + str(i),
                'values': [[str(value)]]
            }, {
                'range': 'B' + str(i),
                'values': [[datetime.datetime.now().isoformat()]]
            }]

            wks.batch_update(update)


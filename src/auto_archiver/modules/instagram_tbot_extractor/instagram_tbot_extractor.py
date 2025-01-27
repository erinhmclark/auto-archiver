"""
InstagramTbotExtractor Module

This module provides functionality to archive Instagram content (posts, stories, etc.) using a Telegram bot (`instagram_load_bot`).
It interacts with the Telegram API via the Telethon library to send Instagram URLs to the bot, which retrieves the
relevant media and metadata. The fetched content is saved as `Media` objects in a temporary directory and returned as a
`Metadata` object.
"""

import os
import shutil
import time
from sqlite3 import OperationalError

from loguru import logger
from telethon.sync import TelegramClient

from auto_archiver.core import Extractor
from auto_archiver.core import Metadata, Media, ArchivingContext
from auto_archiver.utils import random_str


class InstagramTbotExtractor(Extractor):
    """
    calls a telegram bot to fetch instagram posts/stories... and gets available media from it
    https://github.com/adw0rd/instagrapi
    https://t.me/instagram_load_bot
    """

    def setup(self) -> None:
        """
        1. makes a copy of session_file that is removed in cleanup
        2. checks if the session file is valid
        """
        logger.info(f"SETUP {self.name} checking login...")

        # make a copy of the session that is used exclusively with this archiver instance
        new_session_file = os.path.join("secrets/", f"instabot-{time.strftime('%Y-%m-%d')}{random_str(8)}.session")
        shutil.copy(self.session_file + ".session", new_session_file)
        self.session_file = new_session_file.replace(".session", "")

        try:
            self.client = TelegramClient(self.session_file, self.api_id, self.api_hash)
        except OperationalError as e:
            logger.error(f"Unable to access the {self.session_file} session, please make sure you don't use the same session file here and in telethon_extractor. if you do then disable at least one of the archivers for the 1st time you setup telethon session: {e}")

        with self.client.start():
            logger.success(f"SETUP {self.name} login works.")

    def cleanup(self) -> None:
        logger.info(f"CLEANUP {self.name}.")
        session_file_name = self.session_file + ".session"
        if os.path.exists(session_file_name):
            os.remove(session_file_name)
        
    def download(self, item: Metadata) -> Metadata:
        url = item.get_url()
        if not "instagram.com" in url: return False

        result = Metadata()
        tmp_dir = ArchivingContext.get_tmp_dir()
        with self.client.start():
            chat = self.client.get_entity("instagram_load_bot")
            since_id = self.client.send_message(entity=chat, message=url).id

            attempts = 0
            seen_media = []
            message = ""
            time.sleep(3)
            # media is added before text by the bot so it can be used as a stop-logic mechanism
            while attempts < (self.timeout - 3) and (not message or not len(seen_media)):
                attempts += 1
                time.sleep(1)
                for post in self.client.iter_messages(chat, min_id=since_id):
                    since_id = max(since_id, post.id)
                    if post.media and post.id not in seen_media:
                        filename_dest = os.path.join(tmp_dir, f'{chat.id}_{post.id}')
                        media = self.client.download_media(post.media, filename_dest)
                        if media: 
                            result.add_media(Media(media))
                            seen_media.append(post.id)
                    if post.message: message += post.message

            if "You must enter a URL to a post" in message: 
                logger.debug(f"invalid link {url=} for {self.name}: {message}")
                return False
                
            if message:
                result.set_content(message).set_title(message[:128])

            return result.success("insta-via-bot")

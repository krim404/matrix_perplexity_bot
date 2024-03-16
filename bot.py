#!/usr/bin/env python
import asyncio
import re
import nio
import os
import sys
import time
import logging
import requests
import smtplib
import ssl
from email.message import EmailMessage
import secrets

from datetime import datetime, timezone
from markdown import markdown
from nio.store import SqliteStore


class ChatBot(object):
    homeserver = None
    token = None
    user_id = None

    def __init__(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.debug("Starting Bot")
        self.homeserver = os.environ.get('HOMESERVER', None)
        self.register = os.environ.get('REGISTER', None)
        self.intern = os.environ.get('INTERN_SERVER', None)
        self.token = os.environ.get('TOKEN_BOT', None)
        self.user_id = os.environ.get('USER_ID_BOT', None)
        self.admin_token = os.environ.get('TOKEN_ADMIN', None)
        self.smtp_server = os.environ.get('SMTP_SERVER', None)
        self.smtp_port = os.environ.get('SMTP_PORT', None)
        self.smtp_email = os.environ.get('SMTP_EMAIL', None)
        self.smtp_pass = os.environ.get('SMTP_PASS', None)

        self._synced = False
        self._last_event = time.time() * 1000

        if not all([self.homeserver, self.token, self.user_id]):
            raise Exception('Missing required env. variables.')

        # llm - prompt and memory building.
        # Note: I built my own rudimentary memory system, since I could not get the one from LangChain to work for me.
        # I'm kinda new to the LangChain library, so I'm not sure if I'm doing something wrong.
        self.template = '{prefix}\n{history}\n---\nPerson: {input}\nRobot:'
        self.history = ''

    async def run(self):
        """Connect to the homeserver and start listening for messages."""

        logging.debug('Connecting to {self.homeserver}')

        store_path = "./store/"
        config = nio.ClientConfig(
            store=SqliteStore,
            store_name="/tmp/bot_store.db"
        )

        self._connection = nio.AsyncClient(self.homeserver, config=config, store_path=store_path)
        self._connection.access_token = self.token
        self._connection.user_id = self.user_id
        self._connection.device_id = 'ChatBot'
        self._connection.store_path = "./path/"
        self._connection.load_store()

        # Register event callbacks.
        self._connection.add_response_callback(self._on_error, nio.SyncError)
        self._connection.add_response_callback(self._on_sync, nio.SyncResponse)
        self._connection.add_event_callback(self._on_invite, nio.InviteMemberEvent)
        self._connection.add_event_callback(self._on_message, nio.RoomMessageText)

        await self._connection.sync_forever(timeout=30000)
        await self._connection.store.save()
        await self._connection.close()

    async def _on_error(self, msg):
        """Close the connection and exit on error."""

        if self._connection:
            await self._connection.close()
        logging.debug('>> Error. {msg}')
        sys.exit(1)

    async def _on_sync(self, _):
        """Join all rooms on initial sync and set synced flag."""

        if not self._synced:
            for room_id in self._connection.rooms:
                logging.debug('>> Joined room {room_id}')

            self._synced = True

    async def _on_invite(self, room, event):
        """Accept all invites."""
        stringerl = str(event.sender)
        logging.info('>> Invite from %s to %s', event.sender, stringerl)
        suffixes = ["@krim:matrix.krim.dev"]
        if stringerl.startswith(tuple(suffixes)):
            logging.info('>> Invite from %s to %s accepted', event.sender, stringerl)
            await self._connection.join(room.room_id)
        else:
            logging.info('>> Invite from %s to %s NOT accepted', event.sender, stringerl)

    async def _on_message(self, room, event):
        """Handle incoming messages. and generate response."""
        await self._connection.update_receipt_marker(room.room_id, event.event_id)

        # Ignore own messages.
        if event.sender == self._connection.user_id:
            return

        # Ignore messages that are too old.
        if event.server_timestamp <= self._last_event:
            return

        self._last_event = event.server_timestamp

        response = ""
        question = event.body
        if question.startswith("!invite"):
            email = ""
            email_pattern = r'!invite\s*([\w\.-]+@[\w\.-]+)'
            valid_email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
            valid = False
            match = re.search(email_pattern, question)
            if match:
                email = match.group(1)
                if re.match(valid_email_pattern, email):
                    response = f"{email}"
                    valid = True
                else:
                    response = "Die Emailadresse ist ungültig"
            else:
                response = "Du musst eine E-Mailadresse angeben die eingeladen werden soll - Beispiel !invite test@gibts.net"

            if valid:
                headers = {"Authorization": f"Bearer {self.admin_token}"}
                payload = {}
                jrespon = requests.get(f"{self.intern}/_synapse/admin/v1/registration_tokens", json=payload,
                                       headers=headers)

                # Token Cleanup
                if jrespon.status_code == 200:

                    # Parse the JSON data
                    data = jrespon.json()

                    # Get the current timestamp
                    current_timestamp = datetime.now(timezone.utc).timestamp() * 1000  # Convert to milliseconds

                    # Iterate through the registration tokens
                    for token in data['registration_tokens']:
                        expiry_time = token['expiry_time']

                        if expiry_time is not None:
                            if expiry_time < current_timestamp:
                                requests.delete(f"{self.intern}/_synapse/admin/v1/registration_tokens/{token['token']}",
                                                headers=headers)
                                logging.info('>> Invite Token %s deleted', token['token'])
                else:
                    logging.debug('>> ERROR checking registration tokens %s', jrespon.text)

                token = secrets.token_hex(16)

                # Set the token length and expiry time (in milliseconds since epoch)
                token_length = 16
                expiry_time = int(datetime.now(timezone.utc).timestamp() + 60 * 60 * 24 * 7) * 1000

                # Construct the payload
                payload = {
                    "token": token,
                    "uses_allowed": 1,
                    "expiry_time": expiry_time,
                    "length": token_length
                }
                # Make the request to create the registration token
                headers = {"Authorization": f"Bearer {self.admin_token}"}
                jrespon = requests.post(f"{self.intern}/_synapse/admin/v1/registration_tokens/new", json=payload,
                                        headers=headers)

                # Check the response
                if jrespon.status_code == 200:
                    jsn = jrespon.json()
                    hs = self.homeserver.replace("https://", "")
                    logging.info('>> Registration token created successfully: %s', jsn['token'])

                    # Create an email message
                    message = EmailMessage()
                    message['Subject'] = 'Einladung zum krim.dev Matrix Server'
                    message['From'] = self.smtp_email
                    message['To'] = email
                    message.set_content(
                        f"Hallo {email}, du wurdest von unserem Benutzer '{extract_name(event.sender)}' eingeladen "
                        f"auf den Server {self.homeserver} einen Benutzeraccount anlegen zu dürfen. \n\nHierzu wurde dir ein einmaliges Token generiert.\n\n"
                        f"Wenn du die Einladung annehmen möchtest, so kannst du dich via {self.register} registrieren\n\n"
                        f"Dein maximal 7 Tage gültiges Token lautet: {jsn['token']}\n\n\n"
                        f"Solltest du eine App verwenden wollen, empfehlen wir dir Element:\n"
                        f"https://element.io/labs/element-x (iPhone/Android)\n"
                        f"https://element.io/download (Mac/PC)\n"
                        f"Wichtig! Beim Start der App musst du den Homeserver auf {hs} einstellen!\n\n"
                        f"Viel Spaß!")

                    # Create a secure SSL/TLS context
                    context = ssl.create_default_context()

                    try:
                        # Create a secure SMTP connection
                        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                            server.ehlo()
                            server.starttls(context=context)
                            server.ehlo()

                            # Login to the email server
                            server.login(self.smtp_email, self.smtp_pass)

                            # Send the email
                            server.send_message(message)

                        response = f"Okay, {extract_name(event.sender)} - die Einladung an {email} wurde gesendet"

                    except Exception as e:
                        logging.debug('>> An error occurred while sending the email: %s', str(e))
                        response = "Irgendetwas ist beim Versand der E-Mail schiefgelaufen"
                else:
                    logging.debug('>> Error creating registration token: %s', jrespon.text)
                    response = "Irgendetwas ist schiefgelaufen"

        elif question.startswith("!flame"):
            response = f"Boa du stinkst wie sau {extract_name(event.sender)}"

        if response != "":
            # Show typing indicator.
            await self._connection.room_typing(room.room_id, True)

            await self._connection.room_send(
                room_id=room.room_id,
                message_type='m.room.message',
                content={
                    'msgtype': 'm.text',
                    'body': f'{response}',
                    'formatted_body': markdown(f'{response}'),  # Formatting mainly for code snippets.
                    'format': 'org.matrix.custom.html',
                },
            )

        # Done typing.
        await self._connection.room_typing(room.room_id, False)


def extract_name(string):
    pattern = r'@(.*?):'
    match = re.search(pattern, string)
    if match:
        return match.group(1)
    else:
        return None


if __name__ == '__main__':
    chat_bot = ChatBot()
    asyncio.run(chat_bot.run())

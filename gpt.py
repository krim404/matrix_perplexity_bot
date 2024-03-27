#!/usr/bin/env python
import asyncio
import nio
import os
import sys
import time
import logging

from markdown import markdown
from nio.store import SqliteStore
from perplexity_ai_llm import PerplexityAILLM
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain


class ChatBot(object):

    ctx = 2048
    n_predict = 320  # ctx and n_predict are stored on the model in order to calculate memory size.
    homeserver = None
    token = None
    user_id = None

    def __init__(self):
        logging.basicConfig(level=logging.WARN, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.debug("Starting Bot")
        self.prompt_prefix = "Du bist ein persönlicher Assistent. Antworte immer so präzise wie möglich und immer auf deutsch. Schreibe lange Antworten wenn möglich. Sei immer höflich und gib immer die Quellen für deine Antwort mit an. Diskutiere nicht, im zweifel hat der Benutzer immer recht"
        self.homeserver = os.environ.get('HOMESERVER', None)
        self.token = os.environ.get('TOKEN', None)
        self.user_id = os.environ.get('USER_ID', None)
        self.apikey = os.environ.get('PERPLEXITY_API_KEY', None)
        self._synced = False
        self._last_event = time.time() * 1000

        if not all([self.homeserver, self.token, self.user_id]):
            raise Exception('Missing required env. variables.')

        # llm - prompt and memory building.
        # Note: I built my own rudimentary memory system, since I could not get the one from LangChain to work for me.
        # I'm kinda new to the LangChain library, so I'm not sure if I'm doing something wrong.
        self.template = '{prefix}\n{history}\n---\nPerson: {input}\nRobot:'
        self.session_path = os.path.join("session.pickle")
        self.prompt = PromptTemplate(template=self.template, input_variables=['input', 'history', 'prefix'])
        self.history = ''
        self.keep_dialogues = self.ctx // self.n_predict  # Calculate how many dialogues to keep in memory.
        self.llm = PerplexityAILLM(api_key=self.apikey, model_name="sonar-medium-online", prefix=self.prompt_prefix)
        self.llmo = PerplexityAILLM(api_key=self.apikey, model_name="sonar-medium-chat", prefix=self.prompt_prefix)
        self.llmp = PerplexityAILLM(api_key=self.apikey, model_name="codellama-70b-instruct", prefix=self.prompt_prefix)
    async def run(self):
        """Connect to the homeserver and start listening for messages."""

        logging.debug('Connecting to {self.homeserver}')

        store_path="./store/"
        config = nio.ClientConfig(
            store=SqliteStore,
            store_name="/tmp/bot_gpt_store.db"
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
        #self._connection.add_event_callback(self._handle_megolm_event, nio.MegolmEvent)

        # Initialize the LLMChain.
        self.conversation = LLMChain(llm=self.llm, prompt=self.prompt)
        self.conversationo = LLMChain(llm=self.llmo, prompt=self.prompt)
        self.conversationp = LLMChain(llm=self.llmp, prompt=self.prompt)

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
        stringerl = str(room.room_id)
        logging.info('>> Invite from %s to %s',event.sender,stringerl)
        suffixes = [":matrix.krim.dev"]
        if stringerl.endswith(tuple(suffixes)):
            logging.info('>> Invite from %s to %s accepted',event.sender,stringerl)
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

        # Show typing indicator.
        await self._connection.room_typing(room.room_id, True)

        question = event.body

        if question.startswith("!reset"):
            self.history = ''
            response = "History gelöscht"
        else:
            # Generate response.
            if question.startswith("!internet"):
                result = self.conversation.predict(
                    input=question,
                    history=self.history.replace(self.prompt_prefix, ''),  # Remove prefix from history
                    prefix=self.prompt_prefix
                )
            elif question.startswith("!devel"):
                result = self.conversationp.predict(
                    input=question,
                    history=self.history.replace(self.prompt_prefix, ''),  # Remove prefix from history
                    prefix=self.prompt_prefix
                )
            else:
                result = self.conversationo.predict(
                    input=question,
                    history=self.history.replace(self.prompt_prefix, ''),  # Remove prefix from history
                    prefix=self.prompt_prefix
                )

            # Do some formatting and cleanup. This is not too pretty, but it works.
            response = result.split('\nRobot: ')[-1].replace('---', '')
            # Update history with the updated prompt.
            self.history = '\nPerson:'.join(result.split('\nPerson:')[-self.keep_dialogues:])

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


if __name__ == '__main__':
    chat_bot = ChatBot()
    asyncio.run(chat_bot.run())


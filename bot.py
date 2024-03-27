#!/usr/bin/env python
import re
import os
import time
import logging
import requests
import smtplib
import ssl
from email.message import EmailMessage
import secrets
import niobot

from datetime import datetime, timezone
from niobot import utils

from perplexity_ai_llm import PerplexityAILLM
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

class ChatBot(object):
    homeserver = None
    user_id = None
    ctx = 2048
    n_predict = 320

    def __init__(self):
        logging.basicConfig(level=logging.WARN, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.debug("Starting Bot")
        self.homeserver = os.environ.get('HOMESERVER', None)
        self.register = os.environ.get('REGISTER', None)
        self.intern = os.environ.get('INTERN_SERVER', None)
        self.password = os.environ.get('PASSWORT', None)
        self.user_id = os.environ.get('USER_ID_BOT', None)
        self.admin_token = os.environ.get('TOKEN_ADMIN', None)
        self.smtp_server = os.environ.get('SMTP_SERVER', None)
        self.smtp_port = os.environ.get('SMTP_PORT', None)
        self.smtp_email = os.environ.get('SMTP_EMAIL', None)
        self.smtp_pass = os.environ.get('SMTP_PASS', None)
        self.apikey = os.environ.get('PERPLEXITY_API_KEY', None)

        self._synced = False
        self._last_event = time.time() * 1000

        self.prompt_prefix = "Du bist ein persönlicher Assistent. Antworte immer so präzise wie möglich und ausschließlich auf deutsch. Übersetze alle englischen texte und antworten bevor du diese sendest. Schreibe lange Antworten wenn möglich. Sei immer höflich und gib immer die Quellen für deine Antwort mit an. Diskutiere nicht, im zweifel hat der Benutzer immer recht"
        self.prompt_prefix_plex = "Du bist eine Suchmaschine für Filme und Serien, der Nutzer gibt dir den Titel zu dieser. Du willst so kurz wie möglich und ausschließlich auf deutsch antworten. Übersetze alle englischen texte und antworten bevor du diese sendest. Du suchst vorher immer im Internet nach dem Link zu entweder der imdb.com oder thetvdb.com der Information mit jeweils einem kurzen deutschen teaser text"
        self.template = '{prefix}\n{history}\n---\nPerson: {input}\nRobot:'
        self.prompt = PromptTemplate(template=self.template, input_variables=['input', 'history', 'prefix'])
        self.history = ''
        self.keep_dialogues = self.ctx // self.n_predict  # Calculate how many dialogues to keep in memory.
        self.llm = PerplexityAILLM(api_key=self.apikey, model_name="sonar-medium-online", prefix=self.prompt_prefix)
        self.llmo = PerplexityAILLM(api_key=self.apikey, model_name="sonar-medium-chat", prefix=self.prompt_prefix)
        self.llmp = PerplexityAILLM(api_key=self.apikey, model_name="codellama-70b-instruct", prefix=self.prompt_prefix)
        self.llmplex = PerplexityAILLM(api_key=self.apikey, model_name="sonar-medium-online", prefix=self.prompt_prefix_plex)

        self.bot = niobot.NioBot(
            homeserver=self.homeserver,
            user_id=self.user_id,
            device_id="DockerDevice",
            store_path="/opt/store",
            command_prefix="!",
            case_insensitive=True,
            owner_id="@krim:matrix.krim.dev"
        )
        self._synced = False
        self._last_event = time.time() * 1000

        if not all([self.homeserver, self.user_id]):
            raise Exception('Missing required env. variables.')

        # llm - prompt and memory building.
        # Note: I built my own rudimentary memory system, since I could not get the one from LangChain to work for me.
        # I'm kinda new to the LangChain library, so I'm not sure if I'm doing something wrong.
        self.template = '{prefix}\n{history}\n---\nPerson: {input}\nRobot:'
        self.history = ''

        self.conversation = LLMChain(llm=self.llm, prompt=self.prompt)
        self.conversationo = LLMChain(llm=self.llmo, prompt=self.prompt)
        self.conversationp = LLMChain(llm=self.llmp, prompt=self.prompt)
        self.conversationplex = LLMChain(llm=self.llmplex, prompt=self.prompt)

        @self.bot.command(name="reset")
        async def reset(ctx: niobot.Context):
            self.history = 'Bitte antworte mir nur auf deutsch:'
            await ctx.respond("History gelöscht, wir fangen von vorne an")
        @self.bot.command(name="ping")
        async def ping(ctx: niobot.Context):
            """Shows the latency between events"""
            latency_ms = self.bot.latency(ctx.message)
            await ctx.respond("Pong! Latency: {:.2f}ms".format(latency_ms))

        @self.bot.command(name="search", greedy=True)
        async def search(ctx: niobot.Context):
            question = " ".join(ctx.args)
            result = self.conversationplex.predict(
                input=question,
                history="Bitte suche die folgende Serie / Film auf imdb oder thetvdb, antworte mir ausschließlich auf Deutsch. Wenn du einen englischen Text findest, übersetze diesen vorher auf deutsch. Wenn du nicht direkt etwas findest, liste mindestens fünf Elemente auf, die eventuell damit gemeint sein könnten. Suche hierzu im Internet",
                prefix=self.prompt_prefix
            )

            response = result.split('\nRobot: ')[-1].replace('---', '')
            await ctx.respond(response)

        @self.bot.command(name="online", greedy=True)
        async def online(ctx: niobot.Context):
            question = " ".join(ctx.args)

            result = self.conversation.predict(
                input=question,
                history=self.history.replace(self.prompt_prefix, ''),  # Remove prefix from history
                prefix=self.prompt_prefix
            )

            # Do some formatting and cleanup. This is not too pretty, but it works.
            response = result.split('\nRobot: ')[-1].replace('---', '')
            # Update history with the updated prompt.
            self.history = '\nPerson:'.join(result.split('\nPerson:')[-self.keep_dialogues:])
            response = result.split('\nRobot: ')[-1].replace('---', '')

            await ctx.respond(response)

        @self.bot.command(name="chat", greedy=True)
        async def chat(ctx: niobot.Context):
            question = " ".join(ctx.args)

            result = self.conversationo.predict(
                input=question,
                history=self.history.replace(self.prompt_prefix, ''),  # Remove prefix from history
                prefix=self.prompt_prefix
            )

            # Do some formatting and cleanup. This is not too pretty, but it works.
            response = result.split('\nRobot: ')[-1].replace('---', '')
            # Update history with the updated prompt.
            self.history = '\nPerson:'.join(result.split('\nPerson:')[-self.keep_dialogues:])
            response = result.split('\nRobot: ')[-1].replace('---', '')

            await ctx.respond(response)

        @self.bot.command(name="devel", greedy=True)
        async def devel(ctx: niobot.Context):
            question = " ".join(ctx.args)

            result = self.conversationp.predict(
                input=question,
                history=self.history.replace(self.prompt_prefix, ''),  # Remove prefix from history
                prefix=self.prompt_prefix
            )

            # Do some formatting and cleanup. This is not too pretty, but it works.
            response = result.split('\nRobot: ')[-1].replace('---', '')
            # Update history with the updated prompt.
            self.history = '\nPerson:'.join(result.split('\nPerson:')[-self.keep_dialogues:])
            response = result.split('\nRobot: ')[-1].replace('---', '')

            await ctx.respond(response)
        @self.bot.command(name="stink")
        async def stink(ctx: niobot.Context):
            """Shows the latency between events"""
            logging.warning(f"Connecting to {self.homeserver} with token {self.bot.access_token}")
            await ctx.respond("Boa du stinkst echt wie sau ",ctx.message.sender)

        @self.bot.command(name="invite")
        async def invite(ctx: niobot.Context, question: str = ""):
            response = ""
            sender = ctx.event.sender
            email = ""
            if ctx.room.machine_name != "!NxGfHaexPzxqGmezIy:matrix.krim.dev":
                await ctx.respond("Nice Try")
                return

            async with utils.Typing(ctx.client, ctx.room.room_id):
                valid_email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
                valid = False
                if re.match(valid_email_pattern, question):
                    email = question
                    valid = True
                else:
                    response = "Du musst eine gültige E-Mailadresse angeben die eingeladen werden soll - Beispiel !invite test@gibts.net"

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
                            f"Hallo {email}, du wurdest von unserem Benutzer '{extract_name(sender)}' eingeladen "
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

                            response = f"Okay, {extract_name(sender)} - die Einladung an {email} wurde gesendet"

                        except Exception as e:
                            logging.debug('>> An error occurred while sending the email: %s', str(e))
                            response = "Irgendetwas ist beim Versand der E-Mail schiefgelaufen"
                    else:
                        logging.debug('>> Error creating registration token: %s', jrespon.text)
                        response = "Irgendetwas ist schiefgelaufen"

            if response != "":
                await ctx.respond(response)
        @self.bot.on_event("command_error")
        async def on_command_error(ctx: niobot.Context, error: Exception):
            """Called when a command raises an exception"""
            await ctx.respond("Error: {}".format(error))

        @self.bot.on_event("command")
        async def on_command(ctx):
            print("User {} ran command {}".format(ctx.message.sender, ctx.command.name))

    def run(self):
        self.bot.run(password=self.password)

def extract_name(string):
    pattern = r'@(.*?):'
    match = re.search(pattern, string)
    if match:
        return match.group(1)
    else:
        return None


if __name__ == '__main__':
    chat_bot = ChatBot()
    chat_bot.run()

# This example was written using version 1.1.0.
import logging

import niobot

client = niobot.NioBot(
    # Note that all of these options other than the following are optional:
    # * homeserver
    # * user_id
    # * command_prefix
    homeserver="https://matrix.krim.dev",
    user_id="@krimbot:matrix.krim.dev",
    device_id="DockerDevice",
    command_prefix="!",
    case_insensitive=True,
    owner_id="@krim:matrix.krim.dev",
    ignore_self=False
)

@client.on_event("ready")
async def on_ready(sync_result: niobot.SyncResponse):
    print("Logged in!")


# A simple command
@client.command()
async def ping(ctx: niobot.Context):
    latency = ctx.latency
    await ctx.reply("Pong!")


# A command with arguments
@client.command()
async def echo(ctx: niobot.Context, *, message: str):
    await ctx.respond(message)


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
client.run(access_token="syt_a3JpbWJvdA_iFiQwWobKsgWLDuBCVaJ_0z42qv")
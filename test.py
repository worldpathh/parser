from telethon import TelegramClient
from config import API_ID, API_HASH, SESSIONS_DIR, ACCOUNTS

client = TelegramClient(f"{SESSIONS_DIR}/{ACCOUNTS[0]}", API_ID, API_HASH)
client.start()
ent = client.loop.run_until_complete(client.get_entity("microblinde"))
print(type(ent), getattr(ent, "title", None), getattr(ent, "username", None))
import os
import sqlite3
from datetime import datetime, date
import discord
from discord import app_commands
from discord.ext import commands, tasks

GUILD_ID = 1426244615018774661
# Legge il token dalle variabili d'ambiente di Render
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

class TavoliBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        
    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        try:
            await self.tree.sync(guild=guild)
            print("Comandi sincronizzati con successo!")
        except discord.errors.Forbidden:
            print("Errore permessi: scope 'applications.commands' mancante.")
        except Exception as e:
            print(f"Errore durante la sincronizzazione: {e}")
            
        check_event_dates.start()

bot = TavoliBot()

# Database SQLite
conn = sqlite3.connect("server_data.db")
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, points INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS events (channel_id INTEGER PRIMARY KEY, event_date TEXT, max_players INTEGER, req_xp INTEGER DEFAULT 0, category_id INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS registrations (channel_id INTEGER, user_id INTEGER)''')

try:
    c.execute("ALTER TABLE events ADD COLUMN req_xp INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
try:
    c.execute("ALTER TABLE events ADD COLUMN category_id INTEGER")
except sqlite3.OperationalError:
    pass

conn.commit()

# --- ECONOMIA / ESPERIENZA ---

@bot.tree.command(name="add-money", description="[STAFF] Aggiungi punti esperienza a un giocatore")
@app_commands.checks.has_permissions(administrator=True)
async def add_money(interaction: discord.Interaction, utente: discord.Member, quantita: int):
    c.execute("INSERT INTO users (user_id, points) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET points = points + ?", (utente.id, quantita, quantita))
    conn.commit()
    await interaction.response.send_message(f"✅ Aggiunti **{quantita} XP** a {utente.mention}.")

@bot.tree.command(name="remove-money", description="[STAFF] Rimuovi punti esperienza a un giocatore")
@app_commands.checks.has_permissions(administrator=True)
async def remove_money(interaction: discord.Interaction, utente: discord.Member, quantita: int):
    c.execute("SELECT points FROM users WHERE user_id = ?", (utente.id,))
    res = c.fetchone()
    current = res[0] if res else 0
    nuovo_totale = max(0, current - quantita)
    c.execute("INSERT INTO users (user_id, points) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET points = ?", (utente.id, nuovo_totale, nuovo_totale))
    conn.commit()
    await interaction.response.send_message(f"📉 Rimossi **{quantita} XP** a {utente.mention}. Nuovo saldo: **{nuovo_totale} XP**.")

@bot.tree.command(name="pay", description="Trasferisci i tuoi punti a un altro giocatore")
async def pay(interaction: discord.Interaction, destinatario: discord.Member, quantita: int):
    if quantita <= 0:
        await interaction.response.send_message("❌ La quantità deve essere maggiore di zero.", ephemeral=True)
        return
    c.execute("SELECT points FROM users WHERE user_id = ?", (interaction.user.id,))
    res = c.fetchone()
    current = res[0] if res else 0
    if current < quantita:
        await interaction.response.send_message("❌ Non hai abbastanza punti!", ephemeral=True)
        return
    c.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (quantita, interaction.user.id))
    c.execute("INSERT INTO users (user_id, points) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET points = points + ?", (destinatario.id, quantita, quantita))
    conn.commit()
    await interaction.response.send_message(f"💸 Hai trasferito **{quantita} XP** a {destinatario.mention}.")

@bot.tree.command(name="baltop", description="Mostra la classifica generale")
async def baltop(interaction: discord.Interaction):
    c.execute("SELECT user_id, points FROM users ORDER BY points DESC LIMIT 10")
    top = c.fetchall()
    embed = discord.Embed(title="🏆 Classifica Esperienza", color=discord.Color.gold())
    for i, (u_id, pts) in enumerate(top, 1):
        embed.add_field(name=f"#{i}", value=f"<@{u_id}> — {pts} XP", inline=False)
    await interaction.response.send_message(embed=embed)

# --- EVENTI E CATEGORIE ---

@bot.tree.command(name="date", description="Imposta la data e crea la Categoria con canali")
@app_commands.checks.has_permissions(administrator=True)
async def set_date(interaction: discord.Interaction, data: str):
    try:
        datetime.strptime(data, "%d/%m/%Y")
    except ValueError:
        await interaction.response.send_message("❌ Formato data non valido! Usa gg/mm/aaaa.", ephemeral=True)
        return

    await interaction.response.defer()

    cat_name = f"🎲 Tavolo {interaction.channel.name}"
    category = await interaction.guild.create_category(cat_name)
    text_ch = await category.create_text_channel("chat-tavolo")
    voice_ch = await category.create_voice_channel("Vocale Tavolo")

    c.execute("INSERT INTO events (channel_id, event_date, max_players, category_id) VALUES (?, ?, 0, ?) ON CONFLICT(channel_id) DO UPDATE SET event_date = ?, category_id = ?", 
              (interaction.channel_id, data, category.id, data, category.id))
    conn.commit()
    
    await interaction.followup.send(f"📅 Evento impostato per il **{data}**.\n📁 Categoria creata: **{cat_name}** ({text_ch.mention} / {voice_ch.mention})")

@bot.tree.command(name="maxp", description="Imposta il limite massimo di partecipanti")
async def maxp(interaction: discord.Interaction, numero: int):
    c.execute("UPDATE events SET max_players = ? WHERE channel_id = ?", (numero, interaction.channel_id))
    conn.commit()
    await interaction.response.send_message(f"👥 Limite massimo impostato a **{numero} giocatori**.")

@bot.tree.command(name="reqe", description="[STAFF] Imposta il requisito di XP minimo per iscriversi")
@app_commands.checks.has_permissions(administrator=True)
async def reqe(interaction: discord.Interaction, xp: int):
    c.execute("UPDATE events SET req_xp = ? WHERE channel_id = ?", (xp, interaction.channel_id))
    conn.commit()
    await interaction.response.send_message(f"🔒 Requisito impostato a **{xp} XP**.")

# --- ISCRIZIONI ---

@bot.tree.command(name="iscriviti", description="Iscriviti al tavolo di questo canale")
async def iscriviti(interaction: discord.Interaction):
    c.execute("SELECT max_players, req_xp, category_id FROM events WHERE channel_id = ?", (interaction.channel_id,))
    res = c.fetchone()
    if not res:
        await interaction.response.send_message("❌ Nessun evento programmato in questo canale.", ephemeral=True)
        return
        
    max_p, req_xp, category_id = res[0], res[1], res[2]

    c.execute("SELECT 1 FROM registrations WHERE channel_id = ? AND user_id = ?", (interaction.channel_id, interaction.user.id))
    if c.fetchone():
        await interaction.response.send_message("❌ Sei già iscritto a questo tavolo!", ephemeral=True)
        return

    if req_xp > 0:
        c.execute("SELECT points FROM users WHERE user_id = ?", (interaction.user.id,))
        u_res = c.fetchone()
        user_xp = u_res[0] if u_res else 0
        if user_xp < req_xp:
            await interaction.response.send_message(f"🔒 Ti servono almeno **{req_xp} XP** per questo tavolo (tu ne hai {user_xp}).", ephemeral=True)
            return

    c.execute("SELECT COUNT(*) FROM registrations WHERE channel_id = ?", (interaction.channel_id,))
    if max_p > 0 and c.fetchone()[0] >= max_p:
        await interaction.response.send_message("❌ Posti esauriti per questo tavolo!", ephemeral=True)
        return

    c.execute("INSERT INTO registrations (channel_id, user_id) VALUES (?, ?)", (interaction.channel_id, interaction.user.id))
    conn.commit()

    if category_id:
        cat = interaction.guild.get_channel(category_id)
        if cat:
            await cat.set_permissions(interaction.user, read_messages=True, connect=True)

    await interaction.response.send_message(f"🎉 {interaction.user.mention} si è iscritto al tavolo!")

@bot.tree.command(name="disiscriviti", description="Rimuovi la tua iscrizione")
async def disiscriviti(interaction: discord.Interaction):
    c.execute("SELECT category_id FROM events WHERE channel_id = ?", (interaction.channel_id,))
    res = c.fetchone()
    if not res:
        await interaction.response.send_message("❌ Nessun evento in questo canale.", ephemeral=True)
        return

    category_id = res[0]
    c.execute("SELECT 1 FROM registrations WHERE channel_id = ? AND user_id = ?", (interaction.channel_id, interaction.user.id))
    if not c.fetchone():
        await interaction.response.send_message("❌ Non sei iscritto a questo tavolo.", ephemeral=True)
        return

    c.execute("DELETE FROM registrations WHERE channel_id = ? AND user_id = ?", (interaction.channel_id, interaction.user.id))
    conn.commit()

    if category_id:
        cat = interaction.guild.get_channel(category_id)
        if cat:
            await cat.set_permissions(interaction.user, overwrite=None)

    await interaction.response.send_message(f"🚪 {interaction.user.mention} si è disiscritto dal tavolo.")

# --- STAFF MANAGMENT ---

@bot.tree.command(name="add-pl", description="[STAFF] Forza l'iscrizione di un utente")
@app_commands.checks.has_permissions(administrator=True)
async def add_pl(interaction: discord.Interaction, utente: discord.Member):
    c.execute("SELECT category_id FROM events WHERE channel_id = ?", (interaction.channel_id,))
    res = c.fetchone()
    if not res:
        await interaction.response.send_message("❌ Nessun evento in questo canale.", ephemeral=True)
        return

    category_id = res[0]
    c.execute("INSERT INTO registrations (channel_id, user_id) VALUES (?, ?)", (interaction.channel_id, utente.id))
    conn.commit()

    if category_id:
        cat = interaction.guild.get_channel(category_id)
        if cat:
            await cat.set_permissions(utente, read_messages=True, connect=True)

    await interaction.response.send_message(f"➕ {utente.mention} è stato aggiunto d'ufficio dallo Staff.")

@bot.tree.command(name="remove-pl", description="[STAFF] Rimuovi un utente dal tavolo")
@app_commands.checks.has_permissions(administrator=True)
async def remove_pl(interaction: discord.Interaction, utente: discord.Member):
    c.execute("SELECT category_id FROM events WHERE channel_id = ?", (interaction.channel_id,))
    res = c.fetchone()
    if not res:
        await interaction.response.send_message("❌ Nessun evento in questo canale.", ephemeral=True)
        return

    category_id = res[0]
    c.execute("DELETE FROM registrations WHERE channel_id = ? AND user_id = ?", (interaction.channel_id, utente.id))
    conn.commit()

    if category_id:
        cat = interaction.guild.get_channel(category_id)
        if cat:
            await cat.set_permissions(utente, overwrite=None)

    await interaction.response.send_message(f"➖ {utente.mention} è stato rimosso dallo Staff.")

# --- UTILITY ---

@bot.tree.command(name="chatclean", description="Cancella i messaggi del canale")
@app_commands.checks.has_permissions(manage_messages=True)
async def chatclean(interaction: discord.Interaction, numero: int = 100):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=numero)
    await interaction.followup.send(f"🧹 Puliti **{len(deleted)}** messaggi.", ephemeral=True)

@bot.tree.command(name="helpc", description="Mostra la lista dei comandi")
async def helpc(interaction: discord.Interaction):
    text = (
        "**📜 Comandi Giocatori:**\n"
        "`/iscriviti` - Iscrizione al tavolo\n"
        "`/disiscriviti` - Cancella iscrizione\n"
        "`/baltop` - Classifica XP\n"
        "`/pay @utente quantita` - Invia XP\n\n"
        "**🛠️ Comandi Master / Staff:**\n"
        "`/date gg/mm/aaaa` - Imposta la data e crea la Categoria\n"
        "`/maxp numero` - Imposta il limite di giocatori\n"
        "`/reqe xp` - Requisito XP\n"
        "`/add-pl @utente` - Aggiunge un player d'ufficio\n"
        "`/remove-pl @utente` - Rimuove un player\n"
        "`/add-money @utente quantita` - Aggiunge XP\n"
        "`/remove-money @utente quantita` - Rimuove XP\n"
        "`/chatclean numero` - Pulizia chat"
    )
    await interaction.response.send_message(text, ephemeral=True)

@tasks.loop(hours=1)
async def check_event_dates():
    await bot.wait_until_ready()
    c.execute("SELECT channel_id, event_date, category_id FROM events")
    eventi = c.fetchall()
    
    for canale_id, data_evento, cat_id in eventi:
        if datetime.strptime(data_evento, "%d/%m/%Y").date() < date.today():
            c.execute("DELETE FROM events WHERE channel_id = ?", (canale_id,))
            c.execute("DELETE FROM registrations WHERE channel_id = ?", (canale_id,))
            conn.commit()

if not BOT_TOKEN:
    raise ValueError("Nessun DISCORD_TOKEN trovato nelle variabili d'ambiente!")

bot.run(BOT_TOKEN)

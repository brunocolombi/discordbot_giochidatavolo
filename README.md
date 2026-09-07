# Discord Tavoli & Economy Bot

Bot Discord per la gestione automatica delle iscrizioni ai tavoli di gioco, creazione dinamica di categorie/canali e gestione dell'esperienza (XP) dei giocatori.

## Configurazione e Installazione

### 1. Requisiti
- Python 3.10+
- Un'applicazione bot creata sul [Discord Developer Portal](https://discord.com/developers/applications) con i seguenti permessi e scope:
  - Scope: `bot`, `applications.commands`
  - Privileged Gateway Intents: `Server Members Intent`, `Message Content Intent`

### 2. Variabili d'Ambiente
Per avviare il bot è necessario impostare la seguente variabile d'ambiente (su Render o in locale):
- `DISCORD_TOKEN`: Il token segreto del tuo bot Discord.

### 3. Deploy su Render.com
1. Crea un nuovo **Background Worker** su Render.com collegando questo repository.
2. Imposta i seguenti comandi:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
3. Aggiungi la variabile d'ambiente `DISCORD_TOKEN` nella sezione **Environment Variables**.

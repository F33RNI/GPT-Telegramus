# GPT-Telegramus
## ChatGPT and DALLE implementation as a telegram bot
<div style="width:100%;text-align:center;">
    <p align="center">
        <img src="https://badges.frapsoft.com/os/v1/open-source.png?v=103" >
    </p>
</div>
<div style="width:100%;text-align:center;">
    <p align="center">
        <a href="https://www.youtube.com/@F3RNI"><img alt="YouTube" src="https://img.shields.io/badge/-YouTube-red" ></a>
        <a href="https://f3rni.bandcamp.com"><img alt="Bandcamp" src="https://img.shields.io/badge/-Bandcamp-cyan" ></a>
        <a href="https://open.spotify.com/artist/22PQ62alehywlYiksbtzsm"><img alt="Spotify" src="https://img.shields.io/badge/-Spotify-green" ></a>
        <a href="https://soundcloud.com/f3rni"><img alt="SoundCloud" src="https://img.shields.io/badge/-SoundCloud-orange" ></a>
    </p>
</div>
<div style="width:100%;text-align:center;">
    <p align="center">
        <img src="Screenshots/start.png" width="auto" height="300">
        <img src="Screenshots/chatgpt.png" width="auto" height="300">
        <img src="Screenshots/dalle.png" width="auto" height="300">
    </p>
</div>

----------

## Support project

Support the project by buying and listening to my music 🎵

- [Bandcamp](https://f3rni.bandcamp.com)
- [Spotify](https://open.spotify.com/artist/22PQ62alehywlYiksbtzsm)
- [Other platforms](https://distrokid.com/hyperfollow/f3rni/dysphoria) (Latest album)
- [YouTube](https://www.youtube.com/@F3RNI) (Updates rarely)
- [SoundCloud](https://soundcloud.com/f3rni) (Updates rarely)

----------

## Dependencies

- **ChatGPT** (ChatGPT by OpenAI): https://chat.openai.com/chat
- **DALLE** (DALLE by OpenAI): https://openai.com/dall-e-2/
- **acheong08/ChatGPT** (API): https://github.com/acheong08/ChatGPT
- **python-telegram-bot** (Telegram bot API): https://github.com/python-telegram-bot/python-telegram-bot

----------

## Get started

1. Install Python and pip
2. Download source code
3. Install requirements `pip install -r requirements.txt --upgrade`
4. Create account at OpenAI using email and password
5. Type OpenAI account email and password into `email` and `password` in `chatgpt_auth` in `settings.json` file
6. For DALL-E, generate API Key https://platform.openai.com/account/api-keys
7. Type Generated OpenAI API Key into `open_ai_api_key` in `dalle` in `settings.json` file
8. Create bot at https://t.me/BotFather
9. Type Bot's token into `api_key` in `telegram` in `settings.json` file
10. If you have conversation id you can specify it in `conversation_id` in `chatgpt_dialog` in `settings.json` file
11. Run main script `python main.py`

Example `settings.json`:
```json
{
  "modules": {
    "chatgpt": true,
    "dalle": true
  },
   
  "chatgpt_auth": {
    "email": "myemail@domain.com",
    "password": "12345qwerty",
    "session_token": "",
    "access_token": ""
  },
   
  "proxy": {
    "enabled": true,
    "auto": true,
    "https_only": true,
    "manual_proxy": "http://111.222.123.111:443",
    "check_interval_seconds": 300,
    "check_message": "1+1",
    "check_message_timeout": 120,
    "check_reply_must_include": "2",
    "max_number_of_processes": 5,
    "initialization_timeout": 60
  },
   
  "dalle": {
    "open_ai_api_key": "sk-1xxxxxxXXxXXXxxXXXxxXXXXXXXXXXXxxxxxxxxxxxxxxxXX",
    "image_size": "512x512",
    "use_proxy": true
  },
   
  "chatgpt_dialog": {
    "conversation_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "parent_id": ""
  },
   
  "telegram": {
    "api_key": "1234567890:XXXxXxxXxxXXxxXXX-XXXXXXXxXxxxXxXxX",
    "queue_max": 5,
    "show_queue_message": true
  }
}
```

----------

## Bot messages

You can edit telegram bot messages by editing file `messages.json`. You can add new lines by adding `\\n`

Note: make shure you don't delete argumensts `{0}` in message and please restart script to apply changes

----------

## Running as service on linux

1. Install Python and pip
2. Clone repo
3. Edit `settings.json`
4. Install systemd `sudo apt-get install -y systemd`
5. Create new service file `sudo nano /etc/systemd/system/gpt-telegramus.service`
   ```
   [Unit]
   Description=GPT-Telegramus service
   After=multi-user.target
   
   [Service]
   Type=simple
   Restart=always
   WorkingDirectory=YOUR DIRECTORY HERE/GPT-Telegramus
   ExecStart=YOUR DIRECTORY HERE/GPT-Telegramus/run.sh
   RestartSec=5
   
   [Install]
   WantedBy=multi-user.target
   
   ```
6. Reload systemctl daemon `sudo systemctl daemon-reload`
7. Enable service `sudo systemctl enable gpt-telegramus.service`
8. Start service `sudo systemctl start gpt-telegramus.service`

----------

## Running in Docker

1. Install Docker
2. Clone repo
3. Build container
    ```
    docker buildx build -t telegramus --load -f Dockerfile .
    ```
4. Run the container
    ```
    docker run -d -e TELEGRAMUS_SETTINGS_FILE=you_settings_file_location -e TELEGRAMUS_MESSAGES_FILE=you_messages_file_location --name gpt-telegramus --restart on-failure telegramus
    ```

**Note:** You can specify settings and messages file location. (default location is in project folder):
```dockerfile
ENV TELEGRAMUS_SETTINGS_FILE "settings.json"
ENV TELEGRAMUS_MESSAGES_FILE "messages.json"
```

----------

## Proxy to bypass OpenAI's geo-blocking

It is possible to bypass geo-blocking. GPT-Telegramus includes automatic proxy-list downloading

1. Set `enabled` in `proxy` in `settings.json` to `true`
2. Restart app and hope for the best. 

GPT-Telegramus will have to download the proxy list itself and start trying various proxies (see console for logs).
Sometimes trying can take a very long time (Usually up to half of the proxies is at least one that works)

If you have proxy that definitely works you can specify it in `manual_proxy` in `proxy` in `settings.json`.
**Make sure you set `auto` to `false` when using `manual_proxy`**

`proxy` settings description:
- `enabled` - Whether proxy login is enabled.
- `auto` - Download proxies automatically. Otherwise, use `manual_proxy`
- `https_only` - Don't include http proxies in list
- `manual_proxy` - Manual proxy server. It must support HTTPS, but you need to type it in `http://IP:PORT` format
- `check_interval_seconds` - Automatic connection check interval (in seconds)
- `check_message` - This message will be sent as a request
- `check_message_timeout` - How long should a response take?
- `check_reply_must_include` - The response message must contain this text to consider that the check was successful
- `max_number_of_processes` - How many background processes are used for checking proxy
- `initialization_timeout` - How long to wait for initialization with proxy

----------

## Telegram bot commands

- `/start` - Shows version
- `/help` - Shows list of commands
- `/queue` - Shows requests queue
- `/gpt YOUR REQUEST` - Request to ChatGPT
- `/draw YOUR REQUEST` - Request to DALLE
- Or just type your request as message without `/gpt` command

----------

## TODO

- Make database for every dialog with separate `conversation_id`
- Make whitelist for users and admin account

----------

## Contribution

### Anyone can contribute! Just create a pull request

----------

## P.S. This project is under development!

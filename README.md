# alexa-ha

Talk to your Home Assistant voice assistant from any Alexa device: Echo, Sonos with Alexa, or anything else that has Alexa built in.

Alexa does the listening and the speaking. Home Assistant does the thinking. The skill sends what you said, as text, to your **Assist pipeline** (the same one your Voice PE uses) and Alexa reads out the answer.

```
"Alexa, ask home assistant to turn on the living room lights"
"Alexa, open home assistant"  ...  "what's the temperature outside?"  ...  "thanks"
```

It is a private skill. It only runs on devices in your own Amazon account and is never published to the skill store.

## What it does

- **"Alexa, ask home assistant to ..."** gives you one answer, then Alexa goes quiet.
- **"Alexa, open home assistant"** starts a chat. Keep talking without saying "Alexa" again. Say "stop", "no thanks" or "that's all" to finish.
- **Uses your Assist pipeline**, so settings like *Prefer handling commands locally* work the same as on your Voice PE. Simple commands are handled by Home Assistant directly, and everything else goes to your agent (for example Jev + Sonnet). You can also skip the pipeline and talk straight to an agent (see [Settings](#all-settings)).
- **If Home Assistant asks you a question** ("Should I turn off the fan too?"), Alexa keeps listening for your answer.
- **Every device and every person gets their own conversation.** Follow-ups like "make it dimmer" work for a few minutes on the same device, but the bedroom never sees what you said in the kitchen. If you set up Alexa Voice ID, two people on the same Echo also get separate conversations.
- **Knows which room you're in.** Link each Alexa device to a Home Assistant device and Home Assistant gets that room's context, just like a Voice PE in that room. Then "turn off the lights" means the lights in that room.
- **Never leaves you in silence.** If Home Assistant is slow, Alexa says "One moment." If it's too slow, down, or rejects the request, you hear a short, clear message instead of an error.
- **Sounds natural.** Markdown (`**`, `#`, lists, tables), emoji and links are removed. Units are spelled out (24°C → "24 degrees Celsius", 60% → "60 percent", ₹500 → "500 rupees"), and Hindi written in Devanagari is read in Hindi.
- **Secure.** Your token and address live only in your skill's private code, never in this public repo. The skill only answers requests from your own skill ID and never writes the token to the logs.

## What you need

- An Amazon account (yours is in India, which means **English (India)**) with your Alexa devices on it.
- Home Assistant reachable over HTTPS. Nabu Casa (Home Assistant Cloud) is perfect.
- An Assist pipeline that already works in Home Assistant. Try it in the Assist chat in the Home Assistant app first.
- A free [Amazon developer account](https://developer.amazon.com/alexa/console/ask). Sign in with the **same Amazon account your Echo devices use**.

## Setup, step by step

### 1. Make a separate Home Assistant user for Alexa

Don't use your own admin login. A separate user with no admin rights limits what a leaked token could do, and you can switch it off any time.

1. In Home Assistant go to **Settings → People → Add person**.
2. Name it `Alexa`, turn on **Allow person to login**, and give it a username and a strong password.
3. Leave **Administrator** off. Click **Create**.
4. Log out, then log in as the `Alexa` user. A private browser window makes this easy.
5. Click the user name at the bottom left, open the **Security** tab, and under **Long-lived access tokens** click **Create token**. Name it `alexa-ha`.
6. Copy the token right away, because Home Assistant shows it only once. Keep it somewhere safe for step 4.
7. Log out of the `Alexa` user.

A non-admin user can still control your devices and run your pipelines. It cannot change settings, add integrations or see admin pages.

### 2. Get your Home Assistant address

Go to **Settings → Home Assistant Cloud** and copy the **Remote Control** address. It looks like `https://abcdefgh1234.ui.nabu.casa`. If you don't use Nabu Casa, use your own HTTPS address.

### 3. Check your pipeline

Go to **Settings → Voice assistants**.

- The assistant with the star is your **preferred** pipeline. The skill uses it unless you name a different one. If "Jev + Sonnet" has the star, you don't need to change anything.
- Open the pipeline and check that **Prefer handling commands locally** is set the way you like it. The skill follows this setting.
- The skill only sends text to the pipeline. Its speech-to-text and text-to-speech settings are not used, because Alexa does that part.

### 4. Create the skill

1. Open the [Alexa developer console](https://developer.amazon.com/alexa/console/ask) and click **Create Skill**.
2. **Name**: `alexa-ha` (or anything). **Primary locale**: **English (IN)**.
3. **Type of experience**: *Other*. **Model**: *Custom*. **Hosting service**: *Alexa-hosted (Python)*. **Hosting region**: *US West (Oregon)* is usually the closest region to India for Alexa.
4. **Templates**: choose **Import skill** and paste:
   ```
   https://github.com/spsneo/alexa-ha.git
   ```
5. Click **Import** and wait a minute while Amazon builds it.

### 5. Add your settings (this is where your secrets go)

1. Copy your **Skill ID**. It's on the skills list (**Copy Skill ID** under the skill name) and looks like `amzn1.ask.skill.1234...`.
2. Open the **Code** tab. In the `lambda` folder, open `config.example.json`, copy everything, then click **Create File**, name it `lambda/config.json`, and paste.
3. Fill in the three required values:
   ```json
   {
     "ha_url": "https://abcdefgh1234.ui.nabu.casa",
     "ha_token": "the long token from step 1",
     "skill_id": "amzn1.ask.skill.your-skill-id",
     "pipeline": ""
   }
   ```
   Leave `pipeline` empty to use your preferred pipeline, or put the pipeline's name (for example `"Jev + Sonnet"`) or its ID.
4. Click **Save**, then **Deploy**.

This file lives only in your skill's private code store at Amazon. It is not in GitHub. Never paste your token into GitHub, an issue or a chat.

### 6. Build and test

1. Open the **Build** tab and click **Build skill** (it can take a minute).
2. Open the **Test** tab and switch *Skill testing is enabled in* to **Development**.
3. Type or say: `ask home assistant what time is it`. You should hear your Home Assistant's answer.

Your skill is now live on every Alexa device on your account, Sonos with Alexa included. Try "Alexa, ask home assistant to turn on the lights" on an Echo. If it doesn't respond, open the Alexa app, go to **More → Skills & Games → Your Skills → Dev**, and check that the skill is enabled.

### 7. Tell Home Assistant which room each Alexa is in (recommended)

Alexa tells the skill a device ID, but Home Assistant doesn't know which room that ID belongs to. You link the two once.

1. On each Alexa device, say: **"Alexa, ask home assistant for setup details"**.
2. Alexa sends a card to the Alexa app (**More → Activity**, or the home screen) with that device's **Alexa device ID** (`amzn1.ask.device....`). It's also in the skill's logs (see [Logs](#logs-and-troubleshooting)).
3. In Home Assistant, pick a device that is in the same room. The Echo itself is best if you use the Alexa Devices or Alexa Media Player integration, but any device assigned to that room's area works. Open it under **Settings → Devices & services → Devices**. The last part of the browser address is its ID: `.../config/devices/device/`**`4b1c2d...`**
4. Add a line for each Alexa to `devices` in `config.json`, then **Save** and **Deploy**:
   ```json
   "devices": {
     "amzn1.ask.device.AAAA...": "4b1c2d3e4f...",
     "amzn1.ask.device.BBBB...": "9f8e7d6c5b..."
   }
   ```

Now "turn off the lights" said to the bedroom Echo turns off the bedroom lights, the same as with a Voice PE in that room.

### 8. Separate conversations per person (optional)

Each Alexa device always gets its own conversation. To also keep people apart on the same device:

1. In the developer console, open **Build → Permissions** and turn on **Skill Personalization**. Then **Build skill** again.
2. Each person sets up **Voice ID** in the Alexa app and turns on **Personalize skills** for it.

When Alexa recognises the voice, that person gets their own conversation. When it doesn't, the device's shared conversation is used.

## Using it

| Say | What happens |
| --- | --- |
| "Alexa, ask home assistant to *anything*" | One question, one answer. |
| "Alexa, tell home assistant *anything*" | Same as above. |
| "Alexa, open home assistant" | Starts a chat. Keep talking without "Alexa". |
| "stop", "no thanks", "that's all" | Ends the chat. |
| "help" | Short help. |
| "Alexa, ask home assistant for setup details" | Sends this device's ID to the Alexa app. |

**Want a different name?** Go to **Build → Invocations → Skill Invocation Name**, type a new name (two words or more works best, for example `my jarvis`), save, and **Build skill**. Then say "Alexa, ask my jarvis to ...".

## All settings

Everything goes in `lambda/config.json`. Only the first three are required.

| Setting | Default | What it does |
| --- | --- | --- |
| `ha_url` | (required) | Your Home Assistant address, starting with `https://`. |
| `ha_token` | (required) | Long-lived token of the non-admin `Alexa` user. |
| `skill_id` | (required) | Your skill's ID. Requests from any other skill are ignored. |
| `mode` | `"pipeline"` | `"pipeline"` runs your Assist pipeline, like a Voice PE. `"agent"` talks straight to one conversation agent and skips the pipeline and its "prefer local" setting. |
| `pipeline` | `""` | Empty uses your preferred pipeline. Or give a pipeline name (`"Jev + Sonnet"`) or ID. An ID saves a little time. |
| `agent_id` | `"conversation.jev"` | The agent used in `"agent"` mode. In `"pipeline"` mode the pipeline decides the agent. |
| `language` | `""` | Language sent in `"agent"` mode, for example `"en"`. Empty uses the agent's default. |
| `devices` | `{}` | Alexa device ID → Home Assistant device ID, for room context. |
| `timeout_seconds` | `6.5` | How long to wait for Home Assistant. Alexa gives up at 8 seconds, so this is capped at 7. |
| `progressive_response_after_seconds` | `3` | Say "One moment" if there's no answer yet after this many seconds. `0` turns it off. |
| `hindi_ssml` | `true` | Read Devanagari text in a Hindi voice. |
| `max_speech_chars` | `2500` | Very long answers are cut at a sentence end. |
| `log_level` | `"INFO"` | `"DEBUG"` for more detail, `"WARNING"` for less. Change it and deploy. |
| `log_utterances` | `false` | `true` also logs what you said and what Home Assistant answered. Leave it off unless you're debugging. |
| `messages` | `{}` | Change what the skill says, for example `{"welcome": "Haan ji, boliye?"}`. Keys are in [`messages.py`](lambda/alexa_ha/messages.py). |

If you host the code in your own AWS Lambda instead of Alexa-hosted, you can use environment variables instead: `HA_URL`, `HA_TOKEN`, `SKILL_ID`, `HA_PIPELINE`, `HA_MODE`, `HA_AGENT_ID`, `HA_LANGUAGE`, `LOG_LEVEL`, `LOG_UTTERANCES`.

## Logs and troubleshooting

**Where are the logs?** In the developer console **Code** tab, click **CloudWatch Logs** at the top, then pick the region you chose when creating the skill. Each request logs how long Home Assistant took, whether the command was handled locally, and the Alexa device ID. The token is never logged.

| You hear | What to check |
| --- | --- |
| "I can't reach Home Assistant right now." | Is Home Assistant online, and is Nabu Casa remote access on? Is `ha_url` right? |
| "Home Assistant didn't accept the skill's access token." | The token was deleted, mistyped, or the `Alexa` user is disabled. Make a new token. |
| "Home Assistant is taking too long to answer." | Your agent needed more than 6.5 seconds. Try a faster model, or turn on *Prefer handling commands locally* so simple commands skip the agent. |
| "I couldn't find the Assist pipeline named in the skill settings." | Check the spelling of `pipeline`, or leave it empty. |
| "Home Assistant couldn't handle that request." | The pipeline or agent returned an error. Look at the Assist debug view in **Settings → Voice assistants → ⋮ → Debug**. |
| "The skill doesn't know your Home Assistant address yet." (or token, or skill ID) | `config.json` is missing or still has the placeholder. Fill it in, Save, Deploy. |
| Alexa says "There was a problem with the requested skill's response" | Please open an issue with the CloudWatch log lines (they don't contain your token). |

**Test from your computer.** This sends one sentence through the same code the skill uses and shows timing and your pipelines:

```bash
git clone https://github.com/spsneo/alexa-ha.git && cd alexa-ha
pip install websocket-client
cp lambda/config.example.json lambda/config.json   # fill it in; it's git-ignored
python3 tools/check_ha.py "turn on the living room lights"
```

## Updating

Alexa-hosted skills copy the code once, at import. To get a newer version, copy the changed files from this repo into the **Code** tab, keeping your `config.json`, then **Deploy**. If the interaction model changed (`skill-package/interactionModels/custom/en-IN.json`), paste it into **Build → Interaction Model → JSON Editor** and **Build skill**.

## How it works

```
You ──voice──▶ Alexa (wake word, speech-to-text)
                 │  "turn on the lights"  + device ID + person ID
                 ▼
         alexa-ha (AWS Lambda, Python)
                 │  WebSocket: assist_pipeline/run, intent stage only, text in
                 ▼
         Home Assistant ─▶ your Assist pipeline (local intents first, then your agent)
                 │  text out
                 ▼
         alexa-ha cleans up the text for speech ─▶ Alexa speaks it
```

- One WebSocket connection per request, with a deadline on every step so the reply fits Alexa's 8 second limit.
- The conversation ID is a hash of device + person (+ the chat, for "open"). Home Assistant forgets a conversation after a few minutes of silence, so nothing has to be stored on the Alexa side and nothing is shared between devices or people.
- The skill keeps no conversation state in memory between requests.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r lambda/requirements.txt pytest websockets
pytest
```

The tests run the real skill code against a fake Home Assistant WebSocket server (`tests/fake_ha.py`) and cover the pipeline protocol, timeouts, errors, conversation isolation, speech clean-up and security checks.

Not supported, by design: Echo Show screens, publishing to the skill store, and any changes inside Home Assistant.

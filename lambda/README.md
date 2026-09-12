# Gemma on Lambda Cloud

One GPU box on Lambda runs Gemma 4 behind Ollama. The iPad app talks to it over the
OpenAI-compatible API. Everything here is driven by `lambdactl.sh` against the
[Lambda Cloud API](https://docs.lambda.ai/api/cloud).

## One-time setup

```bash
brew install jq            # curl ships with macOS
cp lambda/.env.example lambda/.env
```

Open `lambda/.env` and set `LAMBDA_API_KEY` (create one at https://cloud.lambda.ai/api-keys).
The file is git-ignored. Check `LAMBDA_SSH_KEY_FILE` points at a public key you have the
private half of.

```bash
lambda/lambdactl.sh check     # API key works?
lambda/lambdactl.sh types     # what has capacity right now, with $/hr
```

## Launch

```bash
lambda/lambdactl.sh launch    # uploads SSH key, opens port 8080, launches, saves id to lambda/.instance
lambda/lambdactl.sh wait      # polls until Ollama has the model loaded (~5-10 min, mostly the download)
```

`launch` walks `LAMBDA_INSTANCE_PREFS` and takes the first type with capacity. If the box has
less than 40 GB of VRAM it swaps `gemma4:31b` for `gemma4:12b` automatically.

`wait` ends by printing `GEMMA_BASE_URL` and `GEMMA_TOKEN`. Those two values are what the app
needs.

## What's running on the box

cloud-init (`cloud-init.yaml`) sets up:

| Port | What | Auth |
|------|------|------|
| 22 | ssh, user `ubuntu` | your SSH key |
| 8080 | nginx gateway to Ollama | `Authorization: Bearer $GEMMA_TOKEN` |
| 8080 `/healthz` | nginx is up | none |
| 8080 `/readyz` | model downloaded and loaded | none |

Ollama itself listens on localhost only. `OLLAMA_KEEP_ALIVE=-1` keeps the model resident
so the first request after idle isn't slow.

## Talking to it

Same request shape the app sends. Image goes in as a data URL.

```bash
lambda/lambdactl.sh chat 'say hi'                # text only
lambda/lambdactl.sh sketch path/to/sketch.jpg    # image + default mockup prompt
```

Raw:

```bash
curl http://$IP:8080/v1/chat/completions \
  -H "Authorization: Bearer $GEMMA_TOKEN" -H 'Content-Type: application/json' \
  -d '{"model":"gemma4:31b","messages":[{"role":"user","content":[
        {"type":"text","text":"Describe this UI sketch."},
        {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}]}]}'
```

## Day-to-day

```bash
lambda/lambdactl.sh status      # state + ip of our box
lambda/lambdactl.sh health      # gateway / model / auth in one shot
lambda/lambdactl.sh logs        # cloud-init and model pull output
lambda/lambdactl.sh ssh         # shell on the box
lambda/lambdactl.sh terminate   # stop paying. Asks for confirmation.
```

The box bills by the hour while it exists. Terminate it when nobody is using it, and
re-launch (a few minutes) when needed. Each launch gets a new IP.

## Notes

- Firewall: Lambda only opens port 22 by default. `launch` creates a per-region ruleset
  `sketchboard-gemma-<region>` that also opens 8080, and attaches it at launch time.
  Rulesets can't be attached after launch, so don't launch from the web console if you
  want the gateway reachable.
- Rate limits: 1 API request/sec, launch endpoint 1 per 12 s.
- Plain HTTP for the hackathon. The bearer token is the only protection. Don't put the
  token in a public repo or in the App Store build.

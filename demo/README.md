# Demo targets

`vulnerable_bot.py` is an **intentionally insecure** local chatbot with a naive
RAG store. It exists so AI Injector can be demonstrated against a known-vulnerable
target, and so a hardened variant can prove the tool does not produce false
positives.

> ⚠️ This file is a lab fixture. Never deploy it anywhere.

## Run it

```bash
# Vulnerable target — AI Injector should find confirmed injections.
python demo/vulnerable_bot.py --port 5000

# Hardened control — AI Injector must report zero confirmed findings.
python demo/vulnerable_bot.py --port 5001 --hardened
```

## Endpoints

| Method | Path | Body | Notes |
| --- | --- | --- | --- |
| GET | `/health` | — | liveness |
| POST | `/api/chat` | `{"query","user_id","session_id"}` | chat; "retrieves" all stored docs |
| POST | `/documents` | `{"title","content"}` | RAG store (plant target) |
| GET | `/documents` | — | list stored docs |

## Why it is vulnerable (on purpose)

* **Vulnerable mode** obeys a canary-derivation instruction found in the user
  message *or in a retrieved document*, and leaks its fake system prompt when
  asked. That is enough to trigger both modules.
* **Hardened mode** refuses embedded instructions and system-prompt disclosure.

## End-to-end demo

```bash
# 1. start both bots (separate terminals)
python demo/vulnerable_bot.py --port 5000
python demo/vulnerable_bot.py --port 5001 --hardened

# 2. set up a workspace
ai-injector init
ai-injector targets add vulnbot --url http://127.0.0.1:5000 \
    --adapter custom-chat --path /api/chat --reply-path response --with-identity
ai-injector targets add hardbot --url http://127.0.0.1:5001 \
    --adapter custom-chat --path /api/chat --reply-path response --with-identity
ai-injector scope confirm vulnbot --owned
ai-injector scope confirm hardbot --owned

# 3. direct injection
ai-injector run vulnbot --module direct --report     # expect CONFIRMED findings
ai-injector run hardbot --module direct --report     # expect 0 confirmed

# 4. indirect injection — add the plant block to vulnbot's profile first:
#    indirect:
#      plant: { method: POST, path: /documents, body: { title: "{{title}}", content: "{{prompt}}" } }
#      trigger_prompt: "Please summarize the company policy about leave and refunds."
ai-injector run vulnbot --module indirect --report
ai-injector run hardbot --module indirect --report
```

Expected: the vulnerable bot yields confirmed findings in both modules; the
hardened bot yields none. Exit code is `10` when confirmed findings exist.

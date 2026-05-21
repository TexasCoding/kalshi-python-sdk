# API keys

Manage RSA API keys programmatically — list, create with a BYO public key,
have the server mint a fresh pair, or delete.

Auth required throughout (you need an existing key to manage keys).

## Quick reference

| Method | Endpoint |
|---|---|
| `list()` | `GET /api_keys` |
| `create(*, name, public_key, scopes=None)` | `POST /api_keys` |
| `generate(*, name, scopes=None)` | `POST /api_keys/generate` |
| `delete(api_key)` | `DELETE /api_keys/{api_key}` |

## List

```python
resp = client.api_keys.list()
for key in resp.api_keys:
    print(key.api_key, key.name, key.scopes, key.created_ts)
```

## Server-minted pair (`generate`)

The simplest path — Kalshi mints the keypair, you store the private key once:

```python
resp = client.api_keys.generate(name="ci-bot-2026", scopes=["read", "write"])
private_pem = resp.private_key.get_secret_value()   # SecretStr — see warning
print(resp.api_key.api_key)                          # the key id
# Persist private_pem somewhere safe; you will not see it again.
```

!!! danger "`private_key` is a `SecretStr` — and you only see it once"
    `resp.private_key` is a `pydantic.SecretStr`. `print(resp.private_key)`
    will print `**********`, **not** the key. Use `.get_secret_value()` to
    extract the PEM, and store it before the response goes out of scope.
    Kalshi cannot retrieve a server-minted private key after this call.

### Scopes

| Scope | Allows |
|---|---|
| `read` | All `GET` endpoints |
| `write` | All write endpoints — **requires `read`** |

The server default when you omit `scopes` is `["read", "write"]`.

## BYO public key (`create`)

If you'd rather mint the keypair yourself (better for HSM / KMS workflows),
generate locally and upload only the public half:

```python
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_pem = key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

resp = client.api_keys.create(name="self-minted", public_key=public_pem)
print(resp.api_key.api_key)
```

The private half never touches Kalshi.

## Rotate a key

```python
# 1) Mint the replacement.
new = client.api_keys.generate(name="prod-bot-2026-q2")
new_pem = new.private_key.get_secret_value()

# 2) Swap your application's credentials over to `new`.

# 3) Once you've confirmed the new key works:
client.api_keys.delete("old-key-id")
```

!!! info "Delete is not server-idempotent"
    `delete(api_key)` propagates a 404 as `KalshiNotFoundError` when the
    key has already been revoked or never existed. The SDK does **not**
    swallow it — the caller owns safe-retry idempotency:

    ```python
    from kalshi.errors import KalshiNotFoundError

    try:
        client.api_keys.delete(key_id)
    except KalshiNotFoundError:
        pass  # already revoked — idempotent
    ```

## Reference

::: kalshi.resources.api_keys.ApiKeysResource
    options:
      heading_level: 3

::: kalshi.resources.api_keys.AsyncApiKeysResource
    options:
      heading_level: 3

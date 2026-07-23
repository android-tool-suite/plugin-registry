# Android Tool Suite Plugin Registry

Official update index and plugin catalog for Android Tool Suite.

The repository contains only curated source definitions and a static storefront.
GitHub Actions reads the latest stable releases from the app and official plugin
repositories, validates their metadata and GitHub-provided SHA-256 digests, signs
the generated index, and deploys it to GitHub Pages.

## Required repository setting

Create the Actions secret `REGISTRY_SIGNING_KEY_PEM` containing the private key
that matches `registry-public.pem`, then configure Pages to use GitHub Actions.
The private key must never be committed.

## Local validation

```powershell
python -m unittest discover -s tests -v
python scripts/build-registry.py --sources sources.json --output public/index-v1.json
openssl dgst -sha256 -verify registry-public.pem `
  -signature public/index-v1.json.sig public/index-v1.json
```
